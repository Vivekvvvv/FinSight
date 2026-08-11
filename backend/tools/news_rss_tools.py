"""RSS headline tooling extracted from tools.news.

Kept self-contained (no dependency on tools.news) so the news module can
stay focused on the public news APIs; news re-exports every name here for
backward compatibility.
"""
from __future__ import annotations

import logging
import os
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .utils import _normalize_published_date
from backend.utils.env_config import env_int


logger = logging.getLogger(__name__)

# ── RSS-dedicated lightweight session ───────────────────────────



_RSS_SESSION: Optional[requests.Session] = None

_RSS_TIMEOUT = env_int("FINSIGHT_RSS_TIMEOUT", 4, minimum=1)

_RSS_MAX_RETRIES = env_int("FINSIGHT_RSS_MAX_RETRIES", 1, minimum=0)

_MAX_RSS_FEEDS = env_int("FINSIGHT_MAX_RSS_FEEDS", 6, minimum=1)

NEWS_TAG_RULES = [
    ("科技", ["tech", "technology", "software", "hardware", "cloud", "cyber", "科技", "软件", "硬件", "云", "数据中心", "互联网"]),
    ("AI", ["ai", "artificial intelligence", "genai", "大模型", "生成式", "人工智能", "AIGC"]),
    ("半导体", ["semiconductor", "chip", "foundry", "tsmc", "asml", "nvidia", "半导体", "芯片", "晶圆", "光刻"]),
    ("军事", ["military", "defense", "missile", "army", "navy", "weapon", "drone", "军事", "国防", "导弹", "战机", "无人机", "武器"]),
    ("能源", ["oil", "crude", "gas", "lng", "opec", "能源", "石油", "原油", "天然气", "煤炭", "电力"]),
    ("宏观", ["cpi", "ppi", "gdp", "pmi", "fomc", "inflation", "jobs", "payroll", "宏观", "经济", "利率", "通胀", "就业", "非农", "央行"]),
    ("金融", ["bank", "banking", "credit", "bond", "yield", "金融", "银行", "债券", "收益率", "信贷"]),
    ("监管", ["regulator", "regulation", "antitrust", "sec", "doj", "监管", "反垄断", "制裁", "罚款"]),
    ("并购", ["merger", "acquisition", "buyout", "deal", "并购", "收购", "合并", "交易", "要约"]),
    ("财报", ["earnings", "guidance", "revenue", "profit", "业绩", "财报", "营收", "利润", "指引"]),
    ("加密", ["crypto", "bitcoin", "ethereum", "blockchain", "加密", "比特币", "以太坊", "区块链"]),
    ("汽车", ["ev", "electric vehicle", "automotive", "auto", "汽车", "电动车", "新能源车"]),
    ("消费", ["consumer", "retail", "e-commerce", "消费", "零售", "电商"]),
    ("医药", ["pharma", "biotech", "drug", "医疗", "医药", "生物", "疫苗"]),
    ("地产", ["real estate", "property", "housing", "地产", "楼市"]),
    ("地缘", ["geopolitical", "geopolitics", "war", "conflict", "sanction", "地缘", "冲突", "战争"]),
    ("中国", ["china", "chinese", "中国", "大陆"]),
    ("美国", ["united states", "u.s.", "美国", "白宫", "华盛顿"]),
]


def _get_rss_session() -> requests.Session:
    """Lightweight session: 1 retry, short timeout, no aggressive backoff."""
    global _RSS_SESSION
    if _RSS_SESSION is not None:
        return _RSS_SESSION
    retry = Retry(
        total=_RSS_MAX_RETRIES,
        backoff_factor=0.1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=6, pool_maxsize=6)
    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": "FinSight/1.0 NewsBot"})
    _RSS_SESSION = session
    return session


def _rss_get(url: str, timeout: int = _RSS_TIMEOUT) -> requests.Response:
    """HTTP GET using the lightweight RSS session."""
    return _get_rss_session().get(url, timeout=timeout)


def _is_reasonable_headline(text: str, window: str = "") -> bool:
    """简单过滤：需要日期/时间线索，避免百科/介绍类条目。"""
    combined = (window or "") + " " + text
    has_date = re.search(
        r"(\d{4}-\d{2}-\d{2}|\b20\d{2}\b|\b\d{1,2}\s+(hours?|days?)\s+ago\b)",
        combined,
        re.IGNORECASE,
    )
    if not has_date:
        return False
    lowered = combined.lower()
    if "wall street journal" in lowered:
        return False
    return True


def _get_env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except Exception:
        return default


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def _headline_is_useful(title: str, snippet: str = "") -> bool:
    combined = f"{title} {snippet}".strip()
    if not combined:
        return False
    min_chars = _get_env_int("NEWS_MIN_TITLE_CHARS", 10)
    min_words = _get_env_int("NEWS_MIN_TITLE_WORDS", 4)
    if min_chars <= 0 and min_words <= 0:
        return True

    compact = re.sub(r"\s+", "", combined)
    if _contains_cjk(combined):
        if min_chars <= 0:
            return True
        return len(compact) >= min_chars

    word_count = len(re.findall(r"[A-Za-z0-9]+", combined))
    if min_words > 0 and min_chars > 0:
        return not (word_count < min_words and len(compact) < min_chars)
    if min_words > 0:
        return word_count >= min_words
    if min_chars > 0:
        return len(compact) >= min_chars
    return True


def _keyword_match(text: str, keyword: str) -> bool:
    if not keyword:
        return False
    kw = keyword.lower()
    if _contains_cjk(kw):
        return kw in text
    if len(kw) <= 3 and kw.isalpha():
        return re.search(rf"\b{re.escape(kw)}\b", text) is not None
    return kw in text


def _headline_tags(text: str) -> List[str]:
    if not text:
        return []
    text_lower = text.lower()
    max_tags = max(1, _get_env_int("NEWS_TAG_MAX", 3))
    tags: List[str] = []
    for tag, keywords in NEWS_TAG_RULES:
        if any(_keyword_match(text_lower, kw) for kw in keywords):
            tags.append(tag)
            if len(tags) >= max_tags:
                break
    return tags


def _format_headline_line(
    date_str: str,
    title: str,
    source: str,
    url: str = "",
    snippet: str = "",
) -> str:
    tags = _headline_tags(f"{title} {snippet}".strip())
    tag_text = f"[{'/'.join(tags)}] " if tags else ""
    clean_title = (title or "").strip() or "Untitled"
    display_title = f"[{clean_title}]({url})" if url else clean_title
    clean_source = (source or "").strip()
    source_text = f"({clean_source})" if clean_source else ""
    clean_snippet = (snippet or "").strip()
    if len(clean_snippet) > 160:
        clean_snippet = clean_snippet[:157] + "..."
    snippet_text = f" - {clean_snippet}" if clean_snippet else ""
    return f"[{date_str}] {tag_text}{display_title} {source_text}{snippet_text}".strip()


def _domain_from_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        return host.lower().removeprefix("www.")
    except Exception:
        return ""


def _extract_datetime_from_text(text: str, now: datetime) -> Optional[datetime]:
    if not text:
        return None
    lowered = text.lower()

    # Relative English (e.g., "3 hours ago", "2 days ago")
    m = re.search(r"(\d{1,2})\s*(hours?|days?)\s+ago", lowered)
    if m:
        value = int(m.group(1))
        unit = m.group(2)
        if "hour" in unit:
            return now - timedelta(hours=value)
        return now - timedelta(days=value)

    # Relative Chinese (e.g., "3小时前", "2天前", "10分钟前")
    m = re.search(r"(\d{1,2})\s*(小时|天|分钟)前", text)
    if m:
        value = int(m.group(1))
        unit = m.group(2)
        if unit == "小时":
            return now - timedelta(hours=value)
        if unit == "分钟":
            return now - timedelta(minutes=value)
        return now - timedelta(days=value)

    # Absolute date: YYYY-MM-DD or YYYY/MM/DD
    m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", text)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except Exception:
            return None

    # Absolute date: Month DD, YYYY
    m = re.search(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2}),?\s+(\d{4})",
        text,
        re.IGNORECASE,
    )
    if m:
        try:
            month = m.group(1).title()
            day = int(m.group(2))
            year = int(m.group(3))
            month_map = {
                "Jan": 1,
                "Feb": 2,
                "Mar": 3,
                "Apr": 4,
                "May": 5,
                "Jun": 6,
                "Jul": 7,
                "Aug": 8,
                "Sep": 9,
                "Oct": 10,
                "Nov": 11,
                "Dec": 12,
            }
            return datetime(year, month_map[month], day)
        except Exception:
            return None

    return None


def _extract_datetime_from_url(url: str) -> Optional[datetime]:
    if not url:
        return None

    # Patterns like /2025/07/23/ or 2025-07-23
    m = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", url)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except Exception:
            return None

    # Pattern like 20250723 (avoid matching long ids by requiring separators nearby)
    m = re.search(r"(20\d{2})(\d{2})(\d{2})", url)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except Exception:
            return None

    return None


def _build_news_item(
    title: str,
    source: str,
    url: str = "",
    published_at: Any = None,
    snippet: str = "",
    ticker: Optional[str] = None,
    confidence: float = 0.7,
) -> Dict[str, Any]:
    if not title:
        return {}
    normalized_url = (url or "").strip()
    if "finnhub.io/api/news" in normalized_url.lower():
        normalized_url = ""
    published_date = _normalize_published_date(published_at)
    # Compute tags from headline + snippet for structured output
    tags = _headline_tags(f"{title} {snippet}".strip())
    return {
        "headline": title,
        "title": title,
        "url": normalized_url,
        "source": source or "Unknown",
        "snippet": snippet or "",
        "published_at": published_date,
        "datetime": published_date,
        "ticker": ticker,
        "confidence": confidence,
        "tags": tags,
    }


def format_news_items(items: List[Dict[str, Any]], title: str = "Latest News") -> str:
    if not items:
        return "No recent news available."
    lines: List[str] = []
    for idx, item in enumerate(items, 1):
        headline = item.get("headline") or item.get("title") or "No title"
        source = item.get("source") or "Unknown"
        url = item.get("url") or ""
        snippet = item.get("snippet") or ""
        date_str = item.get("published_at") or item.get("datetime") or "Recent"
        line = _format_headline_line(date_str, headline, source, url, snippet)
        lines.append(f"{idx}. {line}")
    return f"{title}:\n" + "\n".join(lines)


def _parse_rss_items(
    xml_text: str,
    limit: int = 5,
    max_age_days: int = 2,
    now: Optional[datetime] = None,
) -> tuple[list[str], bool]:
    now = now or datetime.now(UTC).replace(tzinfo=None)
    lines: List[str] = []
    try:
        root = ET.fromstring(xml_text)
    except Exception as exc:
        logger.debug("news RSS parse failed: %s", type(exc).__name__)
        return [], False

    items = root.findall(".//item")
    for item in items:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        if not title or not pub_date:
            continue
        if not _headline_is_useful(title, ""):
            continue

        try:
            dt = parsedate_to_datetime(pub_date)
        except Exception:
            dt = None
        if not dt:
            continue
        if dt.tzinfo:
            # 归一到 UTC（naive），与 now 的 naive-UTC 基准一致。此前用
            # astimezone(tz=None) 转成服务器本地时区：非 UTC 部署（如中国
            # UTC+8）下 now-dt 偏移一个时区，48h 窗口漏进约 8h 更老的文章，
            # 且 date_str 与 Finnhub 路径（UTC）不一致（R54）。
            dt = dt.astimezone(UTC).replace(tzinfo=None)

        if (now - dt) > timedelta(days=max_age_days):
            continue

        source = _domain_from_url(link)
        date_str = dt.strftime("%Y-%m-%d")
        lines.append(_format_headline_line(date_str, title, source, link))
        if len(lines) >= limit:
            break

    return lines, bool(lines)


def _fetch_rss_headlines(
    feed_urls: List[str],
    limit: int = 5,
    max_age_days: int = 2,
) -> tuple[list[str], bool]:
    all_lines: List[str] = []
    feeds_to_try = feed_urls[:_MAX_RSS_FEEDS]
    for url in feeds_to_try:
        try:
            resp = _rss_get(url, timeout=_RSS_TIMEOUT)
            if resp.status_code != 200:
                continue
            lines, ok = _parse_rss_items(resp.text, limit=limit, max_age_days=max_age_days)
            if ok:
                all_lines.extend(lines)
        except Exception as exc:
            logger.debug("news RSS request failed: %s", type(exc).__name__)
            continue
        if len(all_lines) >= limit:
            break
    return all_lines[:limit], bool(all_lines)
