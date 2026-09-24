# -*- coding: utf-8 -*-
"""Search/finnhub news and event-date helpers extracted from news.py (round 20)."""

from __future__ import annotations

import logging
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any, Dict, List, Optional

from .env import finnhub_client
from backend.utils.quote import safe_float

from backend.tools.news_rss_tools import (
    _build_news_item,
    _domain_from_url,
    _extract_datetime_from_text,
    _extract_datetime_from_url,
    _format_headline_line,
    _headline_is_useful,
)

logger = logging.getLogger(__name__)



def _extract_search_items(text: str) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    current: Dict[str, str] | None = None

    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"^\d+\.", stripped):
            if current:
                items.append(current)
            title = re.sub(r"^\d+\.\s*", "", stripped).strip()
            current = {"title": title, "snippet": "", "url": ""}
            continue
        if stripped.startswith("http"):
            if current and not current.get("url"):
                current["url"] = stripped
            continue
        if stripped and current and not current.get("snippet"):
            current["snippet"] = stripped

    if current:
        items.append(current)

    return items


def _format_search_news_items(
    text: str,
    limit: int = 5,
    max_age_days: int = 7,
    now: Optional[datetime] = None,
) -> tuple[list[str], bool]:
    now = now or datetime.now(UTC).replace(tzinfo=None)
    items = _extract_search_items(text)
    enriched = []

    for item in items:
        title = item.get("title", "")
        snippet = item.get("snippet", "")
        if not _headline_is_useful(title, snippet):
            continue
        candidate_text = f"{title} {snippet}"
        dt = _extract_datetime_from_text(candidate_text, now)
        if not dt and item.get("url"):
            dt = _extract_datetime_from_url(item["url"])
        age_days = (now - dt).days if dt else None
        url = item.get("url", "")
        source = _domain_from_url(url)
        enriched.append(
            {
                "title": title,
                "snippet": snippet,
                "url": url,
                "source": source,
                "date": dt,
                "age_days": age_days,
            }
        )

    recent = [
        item
        for item in enriched
        if item["date"] and (now - item["date"]) <= timedelta(days=max_age_days)
    ]
    use_items = recent if recent else enriched

    lines: List[str] = []
    for item in use_items[:limit]:
        date_str = item["date"].strftime("%Y-%m-%d") if item["date"] else "未知日期"
        source = item["source"] or "source"
        url = item["url"] or ""
        lines.append(
            _format_headline_line(
                date_str,
                item["title"],
                source,
                url,
                item.get("snippet", ""),
            )
        )

    return lines, bool(recent)


def _build_search_news_items(
    text: str,
    limit: int = 5,
    max_age_days: int = 7,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    now = now or datetime.now(UTC).replace(tzinfo=None)
    items = _extract_search_items(text)
    enriched = []

    for item in items:
        title = item.get("title", "")
        snippet = item.get("snippet", "")
        if not _headline_is_useful(title, snippet):
            continue
        candidate_text = f"{title} {snippet}"
        dt = _extract_datetime_from_text(candidate_text, now)
        if not dt and item.get("url"):
            dt = _extract_datetime_from_url(item["url"])
        age_days = (now - dt).days if dt else None
        url = item.get("url", "")
        source = _domain_from_url(url)
        enriched.append(
            {
                "title": title,
                "snippet": snippet,
                "url": url,
                "source": source,
                "date": dt,
                "age_days": age_days,
            }
        )

    recent = [
        item
        for item in enriched
        if item["date"] and (now - item["date"]) <= timedelta(days=max_age_days)
    ]
    use_items = recent if recent else enriched

    results: List[Dict[str, Any]] = []
    for item in use_items[:limit]:
        published_at = item["date"].strftime("%Y-%m-%d") if item["date"] else None
        results.append(
            _build_news_item(
                title=item["title"],
                source=item["source"] or "search",
                url=item["url"],
                published_at=published_at,
                snippet=item.get("snippet", ""),
                confidence=0.4,
            )
        )
    return [item for item in results if item]


def _fetch_finnhub_market_news(limit: int = 5, max_age_hours: int = 48) -> tuple[list[str], bool]:
    if not finnhub_client:
        return [], False

    now = datetime.now(UTC).replace(tzinfo=None)
    try:
        items = finnhub_client.general_news("general")
    except Exception as exc:
        logger.debug("Finnhub market news fetch failed: %s", type(exc).__name__)
        return [], False

    # 解析循环在 try 之外：非 dict 条目（或非 list 的 items）会让
    # AttributeError/TypeError 逃逸到 get_market_news_headlines——无外层
    # try 时整个市场要闻工具崩，而非走下一兜底。按条跳过（同 R107）。
    if not isinstance(items, (list, tuple)):
        items = []
    lines = []
    for item in items:
        if not isinstance(item, dict):
            continue
        ts = item.get("datetime")
        if not ts:
            continue
        try:
            dt = datetime.utcfromtimestamp(ts)
        except Exception:
            continue
        if (now - dt) > timedelta(hours=max_age_hours):
            continue
        title = item.get("headline") or item.get("summary") or "No title"
        snippet = item.get("summary") or ""
        if not _headline_is_useful(title, snippet):
            continue
        source = item.get("source") or "finnhub"
        url = item.get("url") or ""
        lines.append(
            _format_headline_line(
                dt.strftime("%Y-%m-%d"),
                title,
                source,
                url,
                snippet,
            )
        )
        if len(lines) >= limit:
            break
    return lines, bool(lines)


def _to_date_candidate(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, (int, float)):
        try:
            timestamp = safe_float(value)
            return datetime.utcfromtimestamp(timestamp).date() if timestamp is not None else None
        except Exception:
            return None

    text = str(value).strip()
    if not text:
        return None

    text = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except Exception:
        pass

    fmts = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%b %d, %Y",
        "%B %d, %Y",
        "%d %b %Y",
        "%d %B %Y",
    ]
    for fmt in fmts:
        try:
            return datetime.strptime(text, fmt).date()
        except Exception:
            continue
    return None


def _within_window(candidate: Optional[date], start_date: date, end_date: date) -> bool:
    if candidate is None:
        return False
    return start_date <= candidate <= end_date
