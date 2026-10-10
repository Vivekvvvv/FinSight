"""Screener provider + item-building helpers extracted from tools.screener.

Kept self-contained (no dependency on tools.screener) so the screener module
can stay focused on the public screen_stocks orchestration; screener re-exports
every name here for backward compatibility.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import yfinance as yf

from backend.tools._item import iter_dict_items
from backend.tools.env import ALPHA_VANTAGE_API_KEY
from backend.tools.http import _http_get
from backend.tools.cn_hk_market import fetch_cn_hk_quote_metrics
from backend.utils.quote import safe_float
from backend.tools.screener_static_data import (
    _POPULAR_TICKERS,
    _STATIC_FALLBACK_ITEMS,
    _STATIC_US_FALLBACK_ITEMS,
)


logger = logging.getLogger(__name__)





_ALPHA_TOP_MOVERS_URL = "https://www.alphavantage.co/query"


_ALPHA_TOP_MOVERS_CACHE: dict[str, Any] = {"expires_at": 0.0, "items": None}


_ALPHA_TOP_MOVERS_TTL_SECONDS = 120


_CN_HK_LIVE_UNAVAILABLE_UNTIL: dict[str, float] = {"CN": 0.0, "HK": 0.0}


_CN_HK_LIVE_COOLDOWN_SECONDS = 180


_YF_SCREENER_MAP = {
    "US": "most_actives",  # Most active US stocks
    "CN": "most_actives",  # Fallback - yfinance doesn't have CN-specific
    "HK": "most_actives",  # Fallback
}





def _yfinance_screen_stocks(
    market: str,
    filters: dict[str, Any] | None,
    limit: int,
    sort_by: str,
    sort_order: str,
) -> dict[str, Any]:
    """Fallback screener using yfinance when FMP is unavailable."""
    market_norm = str(market or "US").strip().upper()

    # Directly use popular stocks approach - more reliable than Screener API
    return _yfinance_popular_stocks(market_norm, filters, limit, sort_by, sort_order)



def _static_screen_stocks(
    market: str,
    filters: dict[str, Any] | None,
    limit: int,
    sort_by: str,
    sort_order: str,
    *,
    warning: str = "demo_market_fallback",
) -> dict[str, Any]:
    market_norm = str(market or "US").strip().upper()
    active_filters = filters if isinstance(filters, dict) else {}
    items = _sort_screener_items(_static_fallback_items(market_norm, active_filters), sort_by, sort_order)
    sliced = items[:limit]
    return {
        "success": True,
        "market": market_norm,
        "filters": active_filters,
        "sort": {"by": sort_by, "order": sort_order},
        "items": sliced,
        "count": len(sliced),
        "results": sliced,
        "source": "static_market_demo",
        "warning": warning if sliced else "empty_result",
        "capability_note": "实时筛选数据暂不可用，当前使用内置候选池。",
    }



def _parse_percent(value: Any) -> float | None:
    if value is None:
        return None
    return _clean_float(str(value).strip().rstrip("%"))



def _alpha_vantage_screen_stocks(
    market: str,
    filters: dict[str, Any] | None,
    limit: int,
    sort_by: str,
    sort_order: str,
) -> dict[str, Any] | None:
    """Use Alpha Vantage free top movers when FMP screener is unavailable."""
    market_norm = str(market or "US").strip().upper()
    if market_norm != "US" or not ALPHA_VANTAGE_API_KEY:
        return None

    try:
        now = time.monotonic()
        cached_items = _ALPHA_TOP_MOVERS_CACHE.get("items")
        expires_at = _clean_float(_ALPHA_TOP_MOVERS_CACHE.get("expires_at")) or 0.0
        if isinstance(cached_items, list) and now < expires_at:
            rows = cached_items
        else:
            response = _http_get(
                _ALPHA_TOP_MOVERS_URL,
                params={"function": "TOP_GAINERS_LOSERS", "apikey": ALPHA_VANTAGE_API_KEY},
                timeout=(2, 5),
            )
            if getattr(response, "status_code", 0) != 200:
                logger.info("Alpha Vantage top movers returned a non-success status")
                return None

            raw = response.json()
            if not isinstance(raw, dict) or raw.get("Information") or raw.get("Note"):
                logger.info("Alpha Vantage top movers unavailable")
                return None

            rows = [
                *(raw.get("most_actively_traded") or []),
                *(raw.get("top_gainers") or []),
                *(raw.get("top_losers") or []),
            ]
            _ALPHA_TOP_MOVERS_CACHE["items"] = rows
            _ALPHA_TOP_MOVERS_CACHE["expires_at"] = now + _ALPHA_TOP_MOVERS_TTL_SECONDS
        seen: set[str] = set()
        items: list[dict[str, Any]] = []
        active_filters = filters if isinstance(filters, dict) else {}
        for row in iter_dict_items(rows):
            symbol = str(row.get("ticker") or "").strip().upper()
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)

            price = _clean_float(row.get("price"))
            volume = _clean_float(row.get("volume"))
            change_percent = _parse_percent(row.get("change_percentage"))
            # 有阈值时字段缺失（API 畸形值 → None）判不通过——"price>100"
            # 的结果里不能混入无价格数据的股票；与 us_screener/cn_screener 一致。
            if (threshold := _clean_float(active_filters.get("priceMoreThan"))) is not None and (price is None or price < threshold):
                continue
            if (threshold := _clean_float(active_filters.get("priceLowerThan"))) is not None and (price is None or price > threshold):
                continue
            if (threshold := _clean_float(active_filters.get("volumeMoreThan"))) is not None and (volume is None or volume < threshold):
                continue

            items.append({
                "symbol": symbol,
                "name": symbol,
                "sector": None,
                "industry": "Alpha Vantage top movers",
                "country": "US",
                "exchange": "US",
                "price": price,
                "market_cap": None,
                "volume": volume,
                "beta": None,
                "dividend": None,
                "change_percent": change_percent,
            })
            if len(items) >= max(limit, 50):
                break

        if not items:
            return None

        items = _sort_screener_items(items, sort_by, sort_order)
        sliced = items[:limit]
        return {
            "success": True,
            "market": market_norm,
            "filters": active_filters,
            "sort": {"by": sort_by, "order": sort_order},
            "items": sliced,
            "count": len(sliced),
            "results": sliced,
            "source": "alpha_vantage_top_movers",
            "capability_note": "当前使用 Alpha Vantage 免费热门榜，因为配置的 FMP key 不支持批量筛选接口。",
        }
    except Exception as exc:
        logger.info("Alpha Vantage top movers fallback failed: %s", type(exc).__name__)
        return None



def _yfinance_popular_stocks(
    market: str,
    filters: dict[str, Any] | None,
    limit: int,
    sort_by: str,
    sort_order: str,
) -> dict[str, Any]:
    """Fetch data for popular stocks when screener API fails."""
    market_norm = str(market or "US").strip().upper()

    alpha_result = _alpha_vantage_screen_stocks(market_norm, filters, limit, sort_by, sort_order)
    if alpha_result:
        return alpha_result

    if market_norm in {"CN", "HK"}:
        cnhk_result = _cn_hk_popular_stocks(market_norm, filters, limit, sort_by, sort_order)
        if cnhk_result:
            return cnhk_result

    try:
        items: list[dict[str, Any]] = []
        popular_tickers = _POPULAR_TICKERS.get(market_norm, _POPULAR_TICKERS["US"])

        # Fetch in smaller batches to avoid timeout
        batch_size = min(limit + 5, 15)
        for symbol in popular_tickers[:batch_size]:
            try:
                ticker = yf.Ticker(symbol)
                info = ticker.fast_info

                item = _build_yfinance_item(symbol=symbol, market=market_norm, fast_info=info)
                price = _clean_float(item.get("price"))
                market_cap = _clean_float(item.get("market_cap"))
                volume = _clean_float(item.get("volume"))

                # Apply filters — 有阈值时字段缺失（fast_info 拉取失败 →
                # price/mcap/volume=None）判不通过，与 us_screener/cn_screener 一致。
                if filters:
                    if (threshold := _clean_float(filters.get("priceMoreThan"))) is not None and (price is None or price < threshold):
                        continue
                    if (threshold := _clean_float(filters.get("priceLowerThan"))) is not None and (price is None or price > threshold):
                        continue
                    if (threshold := _clean_float(filters.get("marketCapMoreThan"))) is not None and (market_cap is None or market_cap < threshold):
                        continue
                    if (threshold := _clean_float(filters.get("marketCapLowerThan"))) is not None and (market_cap is None or market_cap > threshold):
                        continue
                    if (threshold := _clean_float(filters.get("volumeMoreThan"))) is not None and (volume is None or volume < threshold):
                        continue

                items.append(item)

                if len(items) >= limit:
                    break
            except Exception:
                continue

        if not items:
            items = _static_fallback_items(market_norm, filters)

        items = _sort_screener_items(items, sort_by, sort_order)
        sliced = items[:limit]
        is_live = bool(sliced) and any(item.get("_live") for item in sliced)
        for item in sliced:
            item.pop("_live", None)

        return {
            "success": True,
            "market": market_norm,
            "filters": filters if isinstance(filters, dict) else {},
            "sort": {"by": sort_by, "order": sort_order},
            "items": sliced,
            "count": len(sliced),
            "results": sliced,
            "source": "yfinance_popular" if is_live else "static_market_demo",
            "warning": None if is_live else "demo_market_fallback",
            "capability_note": (
                f"当前使用 yfinance 热门 {market_norm} 标的，因为 FMP 批量筛选不可用。"
                if is_live
                else "实时筛选数据暂不可用，当前使用内置候选池。"
            ),
        }
    except Exception as exc:
        logger.warning("yfinance popular stocks failed: %s", type(exc).__name__)
        items = _sort_screener_items(_static_fallback_items(market_norm, filters), sort_by, sort_order)
        if items:
            sliced = items[:limit]
            return {
                "success": True,
                "market": market_norm,
                "filters": filters if isinstance(filters, dict) else {},
                "sort": {"by": sort_by, "order": sort_order},
                "items": sliced,
                "count": len(sliced),
                "results": sliced,
                "source": "static_market_demo",
                "warning": "live_fallback_unavailable",
                "capability_note": "实时筛选数据暂不可用，当前使用内置候选池。",
            }
        return {
            "success": False,
            "market": market,
            "items": [],
            "count": 0,
            "error": "yfinance_fallback_failed",
            "source": "yfinance_popular",
        }



def _cn_hk_popular_stocks(
    market: str,
    filters: dict[str, Any] | None,
    limit: int,
    sort_by: str,
    sort_order: str,
) -> dict[str, Any] | None:
    market_norm = str(market or "").strip().upper()
    if market_norm not in {"CN", "HK"}:
        return None

    items: list[dict[str, Any]] = []
    candidates = _POPULAR_TICKERS.get(market_norm, [])
    target_limit = max(1, min(limit, len(candidates) or limit))
    live_allowed = time.monotonic() >= _CN_HK_LIVE_UNAVAILABLE_UNTIL.get(market_norm, 0.0)
    if live_allowed:
        max_live_probes = min(len(candidates), target_limit, 2)
        for symbol in candidates[:max_live_probes]:
            try:
                metrics = fetch_cn_hk_quote_metrics(symbol, timeout=1)
            except Exception:
                metrics = None
            if not isinstance(metrics, dict):
                continue
            item = _build_cn_hk_item(symbol=symbol, market=market_norm, metrics=metrics)
            if not _passes_screener_filters(item, filters):
                continue
            items.append(item)
            if len(items) >= target_limit:
                break

        if not items and max_live_probes:
            _CN_HK_LIVE_UNAVAILABLE_UNTIL[market_norm] = time.monotonic() + _CN_HK_LIVE_COOLDOWN_SECONDS

    seen = {str(item.get("symbol") or "").upper() for item in items}
    used_static_fallback = False
    if len(items) < target_limit:
        for item in _static_fallback_items(market_norm, filters):
            symbol = str(item.get("symbol") or "").upper()
            if not symbol or symbol in seen:
                continue
            items.append(dict(item))
            seen.add(symbol)
            used_static_fallback = True
            if len(items) >= target_limit:
                break

    if not items:
        return {
            "success": True,
            "market": market_norm,
            "filters": filters if isinstance(filters, dict) else {},
            "sort": {"by": sort_by, "order": sort_order},
            "items": [],
            "count": 0,
            "results": [],
            "source": "eastmoney_quote",
            "warning": "coverage_limited_or_empty_result",
            "capability_note": "CN/HK 免费行情源暂时较慢或不可用，可放宽筛选条件后重试。",
        }

    items = _sort_screener_items(items, sort_by, sort_order)
    sliced = items[:target_limit]
    live_count = sum(1 for item in sliced if item.get("_live"))
    live_sources = [
        str(item.get("_source") or "eastmoney_quote")
        for item in sliced
        if item.get("_live")
    ]
    result_source = live_sources[0] if live_sources else "static_market_demo"
    for item in sliced:
        item.pop("_live", None)
        item.pop("_source", None)
    return {
        "success": True,
        "market": market_norm,
        "filters": filters if isinstance(filters, dict) else {},
        "sort": {"by": sort_by, "order": sort_order},
        "items": sliced,
        "count": len(sliced),
        "results": sliced,
        "source": result_source,
        "warning": "live_fallback_unavailable" if used_static_fallback and not live_count else None,
        "capability_note": (
            "当前使用免费行情源；请求较慢的标的会由内置候选池补齐。"
            if live_count
            else "CN/HK 免费行情源暂时较慢，当前使用内置候选池。"
        ),
    }



def _passes_screener_filters(item: dict[str, Any], filters: dict[str, Any] | None) -> bool:
    active = filters if isinstance(filters, dict) else {}
    price = _clean_float(item.get("price"))
    market_cap = _clean_float(item.get("market_cap"))
    volume = _clean_float(item.get("volume"))
    if (threshold := _clean_float(active.get("priceMoreThan"))) is not None and price is not None and price < threshold:
        return False
    if (threshold := _clean_float(active.get("priceLowerThan"))) is not None and price is not None and price > threshold:
        return False
    if (threshold := _clean_float(active.get("marketCapMoreThan"))) is not None and market_cap is not None and market_cap < threshold:
        return False
    if (threshold := _clean_float(active.get("marketCapLowerThan"))) is not None and market_cap is not None and market_cap > threshold:
        return False
    if (threshold := _clean_float(active.get("volumeMoreThan"))) is not None and volume is not None and volume < threshold:
        return False
    return True



def _build_cn_hk_item(*, symbol: str, market: str, metrics: dict[str, Any]) -> dict[str, Any]:
    static_by_symbol = {
        str(item.get("symbol") or "").upper(): item
        for item in iter_dict_items(_STATIC_FALLBACK_ITEMS.get(market, []))
    }
    static = static_by_symbol.get(symbol.upper(), {})
    last_price = _clean_float(metrics.get("last_price"))
    market_cap = _clean_float(metrics.get("market_cap"))
    return {
        "symbol": str(metrics.get("symbol") or symbol).upper(),
        "name": str(metrics.get("name") or static.get("name") or symbol).strip(),
        "sector": static.get("sector"),
        "industry": static.get("industry"),
        "country": market,
        "exchange": static.get("exchange") or ("HKEX" if market == "HK" else "Shanghai/Shenzhen"),
        "price": last_price,
        "market_cap": market_cap,
        "volume": None,
        "beta": None,
        "dividend": None,
        "change_percent": None,
        "_live": True,
        "_source": metrics.get("source") or "eastmoney_quote",
    }



def _get_fast_info_value(info: Any, *names: str) -> Any:
    for name in names:
        if isinstance(info, dict) and name in info:
            return info.get(name)
        value = getattr(info, name, None)
        if value is not None:
            return value
    return None



def _build_yfinance_item(*, symbol: str, market: str, fast_info: Any) -> dict[str, Any]:
    static_by_symbol = {
        str(item.get("symbol") or "").upper(): item
        for item in iter_dict_items(_STATIC_FALLBACK_ITEMS.get(market, []))
    }
    static = static_by_symbol.get(symbol.upper(), {})

    price = _clean_float(_get_fast_info_value(fast_info, "last_price", "lastPrice"))
    market_cap = _clean_float(_get_fast_info_value(fast_info, "market_cap", "marketCap"))
    volume = _clean_float(_get_fast_info_value(fast_info, "last_volume", "lastVolume", "regular_market_volume"))
    previous_close = _clean_float(_get_fast_info_value(fast_info, "previous_close", "previousClose"))
    change_percent = None
    if price is not None and previous_close not in (None, 0):
        change_percent = round((price - previous_close) / previous_close * 100, 4)

    exchange = static.get("exchange")
    if not exchange:
        exchange = "HKEX" if market == "HK" else ("Shanghai/Shenzhen" if market == "CN" else None)

    return {
        "symbol": symbol,
        "name": static.get("name") or symbol,
        "sector": static.get("sector"),
        "industry": static.get("industry"),
        "country": market,
        "exchange": exchange,
        "price": price,
        "market_cap": market_cap,
        "volume": volume,
        "beta": None,
        "dividend": None,
        "change_percent": change_percent,
        "_live": price is not None or market_cap is not None or volume is not None,
    }



def _sort_screener_items(items: list[dict[str, Any]], sort_by: str, sort_order: str) -> list[dict[str, Any]]:
    sort_key_map = {"marketCap": "market_cap", "price": "price", "volume": "volume"}
    py_sort_key = sort_key_map.get(sort_by, "market_cap")
    reverse = sort_order == "desc"
    return sorted(items, key=lambda x: x.get(py_sort_key) or 0, reverse=reverse)



def _static_fallback_items(market: str, filters: dict[str, Any] | None) -> list[dict[str, Any]]:
    market_norm = str(market or "US").strip().upper()
    active_filters = filters if isinstance(filters, dict) else {}
    items: list[dict[str, Any]] = []
    for item in iter_dict_items(_STATIC_FALLBACK_ITEMS.get(market_norm, [])):
        price = _clean_float(item.get("price"))
        market_cap = _clean_float(item.get("market_cap"))
        volume = _clean_float(item.get("volume"))
        if (threshold := _clean_float(active_filters.get("priceMoreThan"))) is not None and price is not None and price < threshold:
            continue
        if (threshold := _clean_float(active_filters.get("priceLowerThan"))) is not None and price is not None and price > threshold:
            continue
        if (threshold := _clean_float(active_filters.get("marketCapMoreThan"))) is not None and market_cap is not None and market_cap < threshold:
            continue
        if (threshold := _clean_float(active_filters.get("marketCapLowerThan"))) is not None and market_cap is not None and market_cap > threshold:
            continue
        if (threshold := _clean_float(active_filters.get("volumeMoreThan"))) is not None and volume is not None and volume < threshold:
            continue
        items.append(dict(item))
    return items



def _static_us_fallback_items(filters: dict[str, Any] | None) -> list[dict[str, Any]]:
    return _static_fallback_items("US", filters)



def _clean_float(value: Any) -> float | None:
    return safe_float(value)
