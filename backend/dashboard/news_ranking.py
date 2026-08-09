"""News ranking helpers for dashboard news scoring.

Extracted from dashboard.data_service to keep the god file shrinking.
"""

from __future__ import annotations

import math
import pandas as pd
from datetime import datetime, timezone
from typing import Any, Optional
from backend.utils.quote import safe_float


_NEWS_RANKING_WEIGHTS: dict[str, dict[str, float]] = {
    "market": {
        "time_decay": 0.45,
        "source_reliability": 0.25,
        "impact_score": 0.2,
        "asset_relevance": 0.1,
    },
    "impact": {
        "time_decay": 0.35,
        "source_reliability": 0.2,
        "impact_score": 0.25,
        "asset_relevance": 0.2,
    },
}


_SOURCE_RELIABILITY_WEIGHTS = {
    "reuters": 0.95,
    "bloomberg": 0.95,
    "wall street journal": 0.9,
    "wsj": 0.9,
    "financial times": 0.9,
    "fitch": 0.88,
    "moody": 0.88,
    "s&p global": 0.88,
    "sec": 0.86,
    "cnbc": 0.82,
    "marketwatch": 0.8,
    "yahoo": 0.72,
    "finnhub": 0.72,
    "alpha vantage": 0.68,
}


_HIGH_IMPACT_KEYWORDS = {
    "earnings",
    "guidance",
    "merger",
    "acquisition",
    "lawsuit",
    "investigation",
    "downgrade",
    "upgrade",
    "layoff",
    "default",
    "bankruptcy",
    "rate hike",
    "rate cut",
    "cpi",
    "inflation",
    "tariff",
}


_MEDIUM_IMPACT_KEYWORDS = {
    "forecast",
    "estimate",
    "partnership",
    "supply",
    "demand",
    "regulation",
    "approval",
    "launch",
    "product",
    "guidance update",
}


_ASSET_ALIAS_WEIGHTS = {
    "GOOGL": {"google", "alphabet"},
    "GOOG": {"google", "alphabet"},
    "META": {"meta", "facebook"},
    "MSFT": {"microsoft"},
    "AAPL": {"apple"},
    "TSLA": {"tesla"},
    "NVDA": {"nvidia"},
    "AMZN": {"amazon"},
}


_NEWS_RANKING_HALF_LIFE_HOURS = {
    "market": 24.0,
    "impact": 36.0,
}


def _ts_seconds(ts: Any) -> Optional[int]:
    if ts is None:
        return None
    try:
        if isinstance(ts, (int, float)):
            return int(ts)
        if isinstance(ts, pd.Timestamp):
            dt = ts.to_pydatetime()
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)  # naive 统一按 UTC，与 datetime 分支一致
            return int(dt.timestamp())
        if isinstance(ts, datetime):
            dt = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        if isinstance(ts, str):
            raw = ts.strip()
            if not raw:
                return None
            iso = raw.replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(iso)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)  # "YYYY-MM-DD" 等 naive 串按 UTC，防本地时区偏移
                return int(parsed.timestamp())
            except ValueError:
                for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
                    try:
                        return int(datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc).timestamp())
                    except ValueError:
                        continue
    except Exception:
        return None
    return None


def _resolve_source_reliability(source: str) -> float:
    text = (source or "").strip().lower()
    if not text:
        return 0.6
    for key, score in _SOURCE_RELIABILITY_WEIGHTS.items():
        if key in text:
            return score
    return 0.65


def _estimate_impact_score(title: str, summary: str) -> float:
    content = f"{title or ''} {summary or ''}".lower()
    high_hits = sum(1 for token in _HIGH_IMPACT_KEYWORDS if token in content)
    medium_hits = sum(1 for token in _MEDIUM_IMPACT_KEYWORDS if token in content)
    score = 0.45 + min(0.35, high_hits * 0.15) + min(0.2, medium_hits * 0.06)
    return max(0.0, min(1.0, score))


def _calculate_time_decay(ts_iso: str, *, half_life_hours: float = 36.0) -> float:
    if not ts_iso:
        return 0.5
    try:
        dt = datetime.fromisoformat(str(ts_iso).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age_hours = max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 3600)
        parsed_half_life = safe_float(half_life_hours)
        safe_half_life = max(1.0, 36.0 if parsed_half_life is None else parsed_half_life)
        return math.exp(-age_hours / safe_half_life)
    except Exception:
        return 0.5


def _build_asset_tokens(symbol: str) -> set[str]:
    normalized_symbol = (symbol or "").strip().upper()
    if not normalized_symbol:
        return set()

    tokens: set[str] = {
        normalized_symbol.lower(),
        normalized_symbol.replace(".", "").lower(),
        normalized_symbol.replace("-", "").lower(),
    }
    tokens.update(_ASSET_ALIAS_WEIGHTS.get(normalized_symbol, set()))
    return {token.strip().lower() for token in tokens if token and token.strip()}


def _estimate_asset_relevance(symbol: str, mode: str, title: str, summary: str) -> float:
    content = f"{title or ''} {summary or ''}".lower()
    if not content:
        return 0.35 if mode == "impact" else 0.4

    tokens = _build_asset_tokens(symbol)
    mention_hits = sum(1 for token in tokens if token in content)

    high_hits = sum(1 for token in _HIGH_IMPACT_KEYWORDS if token in content)
    medium_hits = sum(1 for token in _MEDIUM_IMPACT_KEYWORDS if token in content)

    base = 0.35 if mode == "impact" else 0.4
    mention_boost = min(0.4, mention_hits * (0.2 if mode == "impact" else 0.12))
    keyword_boost = min(0.25, high_hits * 0.05 + medium_hits * 0.02)
    score = base + mention_boost + keyword_boost
    return max(0.0, min(1.0, score))


def _calculate_source_penalty(source: str, source_counts: dict[str, int]) -> float:
    normalized_source = (source or "").strip().lower()
    if not normalized_source:
        return 0.0
    duplicate_count = max(0, source_counts.get(normalized_source, 0) - 1)
    if duplicate_count == 0:
        return 0.0
    return min(0.08, duplicate_count * 0.02)


def _build_ranking_reason(weighted_components: dict[str, float], source_penalty: float) -> str:
    ordered = sorted(weighted_components.items(), key=lambda kv: kv[1], reverse=True)
    dominant = [f"{key}={value:.2f}" for key, value in ordered[:2] if value > 0]
    if source_penalty > 0:
        dominant.append(f"source_penalty=-{source_penalty:.2f}")
    if not dominant:
        return "fallback_scoring"
    return ", ".join(dominant)


def _score_news_item(
    item: dict[str, Any],
    *,
    symbol: str,
    mode: str,
    source_counts: dict[str, int],
) -> dict[str, Any]:
    title = str(item.get("title") or "")
    summary = str(item.get("summary") or "")
    source = str(item.get("source") or "")
    ts = str(item.get("ts") or "")

    weights = _NEWS_RANKING_WEIGHTS.get(mode, _NEWS_RANKING_WEIGHTS["market"])
    half_life_hours = _NEWS_RANKING_HALF_LIFE_HOURS.get(mode, 36.0)

    time_decay = _calculate_time_decay(ts, half_life_hours=half_life_hours)
    source_reliability = _resolve_source_reliability(source)
    impact_score = _estimate_impact_score(title, summary)
    asset_relevance = _estimate_asset_relevance(symbol, mode, title, summary)
    source_penalty = _calculate_source_penalty(source, source_counts)

    weighted_components = {
        "time_decay": time_decay * weights["time_decay"],
        "source_reliability": source_reliability * weights["source_reliability"],
        "impact_score": impact_score * weights["impact_score"],
        "asset_relevance": asset_relevance * weights["asset_relevance"],
    }
    ranking_score = max(0.0, min(1.0, sum(weighted_components.values()) - source_penalty))

    result = dict(item)
    result.update(
        {
            "time_decay": round(time_decay, 6),
            "source_reliability": round(source_reliability, 6),
            "impact_score": round(impact_score, 6),
            "asset_relevance": round(asset_relevance, 6),
            "source_penalty": round(source_penalty, 6),
            "ranking_score": round(ranking_score, 6),
            "ranking_reason": _build_ranking_reason(weighted_components, source_penalty),
            "ranking_factors": {
                "mode": mode,
                "half_life_hours": half_life_hours,
                "weights": {key: round(value, 6) for key, value in weights.items()},
                "weighted": {key: round(value, 6) for key, value in weighted_components.items()},
            },
        }
    )
    return result


def _rank_news_items(items: list[dict[str, Any]], limit: int, *, symbol: str, mode: str) -> list[dict[str, Any]]:
    source_counts: dict[str, int] = {}
    for item in items:
        source_key = str(item.get("source") or "").strip().lower()
        if source_key:
            source_counts[source_key] = source_counts.get(source_key, 0) + 1

    scored = [_score_news_item(item, symbol=symbol, mode=mode, source_counts=source_counts) for item in items]
    scored.sort(
        key=lambda item: (
            -float(item.get("ranking_score") or 0.0),
            -(float(_ts_seconds(item.get("ts")) or 0.0)),
            -float(item.get("impact_score") or 0.0),
            -float(item.get("asset_relevance") or 0.0),
            str(item.get("title") or "").lower(),
            str(item.get("source") or "").lower(),
        )
    )
    return scored[:limit]


def _to_news_item(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        title = item.get("title") or item.get("headline") or ""
        url = item.get("url") or item.get("link") or ""
        source = item.get("source") or item.get("publisher") or ""
        ts = item.get("ts") or item.get("published_at") or item.get("datetime") or ""
        summary = item.get("summary") or item.get("snippet") or item.get("content") or ""
        tags = item.get("tags")  # Phase H: pass through server-computed tags

        if isinstance(ts, (int, float)):
            try:
                ts = datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
            except Exception:
                ts = ""
        elif not isinstance(ts, str):
            ts = str(ts) if ts else ""

        result: dict[str, Any] = {
            "title": str(title).strip(),
            "url": str(url).strip(),
            "source": str(source).strip(),
            "ts": ts,
            "summary": str(summary).strip(),
        }
        # Attach tags if present (Phase H)
        if tags and isinstance(tags, list):
            result["tags"] = tags
        return result

    text = str(item).strip() if item is not None else ""
    return {"title": text, "url": "", "source": "", "ts": "", "summary": ""}


def _parse_news_text(text: str) -> list[dict[str, Any]]:
    """Parse formatted headline text returned by get_market_news_headlines().

    Expected line formats:
      1. [2026-02-10] [Tag] [Title](url) (Source) - Snippet
      2. [2026-02-10] Title (Source) - Snippet
      3. plain title text
    """
    import re as _re

    rows: list[dict[str, Any]] = []
    if not text:
        return rows

    # Patterns for structured extraction
    date_pat = _re.compile(r"\[(\d{4}-\d{2}-\d{2})\]")
    link_pat = _re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
    source_pat = _re.compile(r"\(([A-Za-z][A-Za-z0-9 .&'-]{0,40})\)")

    for line in text.strip().splitlines():
        stripped = line.strip()
        # Skip header lines and very short lines
        if not stripped or len(stripped) < 12:
            continue
        # Skip header-like lines (e.g. "最近48小时市场要闻(RSS):")
        if stripped.endswith(":") and ("要闻" in stripped or "热点" in stripped):
            continue
        # Remove leading numbering "1. ", "2. " etc.
        stripped = _re.sub(r"^\d+\.\s*", "", stripped).strip()
        if not stripped:
            continue

        # Extract date
        ts = ""
        dm = date_pat.search(stripped)
        if dm:
            ts = dm.group(1)

        # Extract markdown link [title](url)
        title = ""
        url = ""
        lm = link_pat.search(stripped)
        if lm:
            title = lm.group(1).strip()
            url = lm.group(2).strip()

        # Extract source (word in parentheses, not a URL)
        source = ""
        for sm in source_pat.finditer(stripped):
            candidate = sm.group(1).strip()
            # Skip if it looks like a URL or is a date
            if "http" in candidate or _re.match(r"^\d{4}-", candidate):
                continue
            source = candidate
            break

        # Extract snippet (text after " - ")
        summary = ""
        dash_idx = stripped.find(" - ", (lm.end() if lm else 0))
        if dash_idx > 0:
            summary = stripped[dash_idx + 3:].strip()

        # Fallback title: use the whole line (cleaned)
        if not title:
            # Remove date bracket, tags, source
            fallback = stripped
            fallback = date_pat.sub("", fallback)
            fallback = _re.sub(r"\[[A-Za-z/]+\]\s*", "", fallback)
            fallback = source_pat.sub("", fallback)
            fallback = fallback.strip(" -")
            title = fallback[:160] if fallback else stripped[:160]

        if title:
            rows.append({
                "title": title,
                "url": url,
                "source": source,
                "ts": ts,
                "summary": summary[:200],
            })
    return rows


def _news_ranking_meta() -> dict[str, Any]:
    return {
        "version": "v2",
        "formula": "sum(weight_i * factor_i) - source_penalty",
        "weights": _NEWS_RANKING_WEIGHTS,
        "half_life_hours": _NEWS_RANKING_HALF_LIFE_HOURS,
        "notes": [
            "ranked by recency, source reliability, impact, and asset relevance",
            "duplicate-source penalty improves feed diversity",
        ],
    }


def _empty_news_payload() -> dict[str, Any]:
    return {
        "market": [],
        "impact": [],
        "market_raw": [],
        "impact_raw": [],
        "ranking_meta": _news_ranking_meta(),
    }
