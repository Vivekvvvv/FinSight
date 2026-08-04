from __future__ import annotations

import logging
import threading
import time
from typing import Any

from backend.tools.http import _http_get
from backend.utils.quote import safe_float

logger = logging.getLogger(__name__)

_NASDAQ_SCREENER_URL = "https://api.nasdaq.com/api/screener/stocks"
_NASDAQ_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.nasdaq.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
}
_CACHE_TTL_SECONDS = 300
_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, Any] = {"expires_at": 0.0, "items": None}


def _number(value: Any) -> float | None:
    if isinstance(value, str):
        value = value.strip().replace("$", "").replace(",", "").replace("%", "")
        if not value or value.lower() in {"n/a", "na", "--"}:
            return None
    return safe_float(value)


def _build_item(row: dict[str, Any]) -> dict[str, Any] | None:
    symbol = str(row.get("symbol") or "").strip().upper()
    if not symbol:
        return None
    return {
        "symbol": symbol,
        "name": str(row.get("name") or symbol).strip() or symbol,
        "sector": str(row.get("sector") or "").strip() or None,
        "industry": str(row.get("industry") or "").strip() or None,
        "country": str(row.get("country") or "US").strip() or "US",
        "exchange": "US",
        "price": _number(row.get("lastsale")),
        "market_cap": _number(row.get("marketCap")),
        "volume": _number(row.get("volume")),
        "beta": None,
        "dividend": None,
        "change_percent": _number(row.get("pctchange")),
    }


def _fetch_items() -> list[dict[str, Any]] | None:
    try:
        response = _http_get(
            _NASDAQ_SCREENER_URL,
            params={"tableonly": "true", "download": "true"},
            headers=_NASDAQ_HEADERS,
            timeout=(3, 20),
        )
        if getattr(response, "status_code", 0) != 200:
            return None
        payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) else None
        rows = data.get("rows") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            return None
        items = [_build_item(row) for row in rows if isinstance(row, dict)]
        return [item for item in items if item is not None]
    except Exception as exc:
        logger.info("Nasdaq public screener failed: %s", type(exc).__name__)
        return None


def _cached_items() -> list[dict[str, Any]] | None:
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _CACHE.get("items")
        if isinstance(cached, list) and now < float(_CACHE.get("expires_at") or 0):
            return [dict(item) for item in cached]

        items = _fetch_items()
        if items is None:
            return None
        _CACHE["items"] = items
        _CACHE["expires_at"] = now + _CACHE_TTL_SECONDS
        return [dict(item) for item in items]


def _passes_filters(item: dict[str, Any], filters: dict[str, Any]) -> bool:
    checks = (
        ("priceMoreThan", "price", lambda actual, threshold: actual >= threshold),
        ("priceLowerThan", "price", lambda actual, threshold: actual <= threshold),
        ("marketCapMoreThan", "market_cap", lambda actual, threshold: actual >= threshold),
        ("marketCapLowerThan", "market_cap", lambda actual, threshold: actual <= threshold),
        ("volumeMoreThan", "volume", lambda actual, threshold: actual >= threshold),
    )
    for filter_key, item_key, predicate in checks:
        threshold = _number(filters.get(filter_key))
        actual = _number(item.get(item_key))
        if threshold is not None and actual is not None and not predicate(actual, threshold):
            return False
    sector = str(filters.get("sector") or "").strip().lower()
    if sector and str(item.get("sector") or "").strip().lower() != sector:
        return False
    industry = str(filters.get("industry") or "").strip().lower()
    if industry and str(item.get("industry") or "").strip().lower() != industry:
        return False
    return True


def nasdaq_screen_stocks(
    *,
    filters: dict[str, Any] | None,
    limit: int,
    page: int,
    sort_by: str,
    sort_order: str,
) -> dict[str, Any] | None:
    items = _cached_items()
    if items is None:
        return None

    active_filters = filters if isinstance(filters, dict) else {}
    filtered = [item for item in items if _passes_filters(item, active_filters)]
    sort_key = {
        "marketCap": "market_cap",
        "price": "price",
        "volume": "volume",
        "changesPercentage": "change_percent",
    }.get(sort_by, "market_cap")
    filtered.sort(key=lambda item: _number(item.get(sort_key)) or 0, reverse=sort_order == "desc")

    limit_norm = max(1, limit)
    page_norm = max(1, page)
    start = (page_norm - 1) * limit_norm
    sliced = filtered[start : start + limit_norm]
    return {
        "success": True,
        "market": "US",
        "filters": active_filters,
        "sort": {"by": sort_by, "order": sort_order},
        "page": page_norm,
        "limit": limit_norm,
        "items": sliced,
        "results": sliced,
        "count": len(sliced),
        "total": len(filtered),
        "source": "nasdaq_public_screener",
        "warning": None if sliced else "empty_result",
        "capability_note": "美股列表来自 Nasdaq 公开股票筛选接口，行情可能存在延迟。",
    }


__all__ = ["nasdaq_screen_stocks"]
