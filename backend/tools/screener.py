from __future__ import annotations

import logging
from typing import Any

import yfinance as yf

from backend.tools.env import ALPHA_VANTAGE_API_KEY, FMP_API_KEY
from backend.tools.http import _http_get
from backend.tools.cn_hk_market import fetch_cn_hk_quote_metrics

logger = logging.getLogger(__name__)

_FMP_SCREENER_URL = "https://financialmodelingprep.com/api/v3/stock-screener"
_ALPHA_TOP_MOVERS_URL = "https://www.alphavantage.co/query"
_ALLOWED_SORT_BY = {
    "marketCap",
    "price",
    "volume",
    "beta",
    "lastAnnualDividend",
    "changesPercentage",
}
_ALLOWED_SORT_ORDER = {"asc", "desc"}

# Yahoo Finance predefined screener keys by market
_YF_SCREENER_MAP = {
    "US": "most_actives",  # Most active US stocks
    "CN": "most_actives",  # Fallback - yfinance doesn't have CN-specific
    "HK": "most_actives",  # Fallback
}

_STATIC_FALLBACK_ITEMS: dict[str, list[dict[str, Any]]] = {
    "US": [
        {
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "country": "US",
            "exchange": "NASDAQ",
            "price": 195.5,
            "market_cap": 3_000_000_000_000,
            "volume": 52_000_000,
            "beta": 1.2,
            "dividend": None,
            "change_percent": 1.19,
        },
        {
            "symbol": "MSFT",
            "name": "Microsoft Corp.",
            "sector": "Technology",
            "industry": "Software",
            "country": "US",
            "exchange": "NASDAQ",
            "price": 430.2,
            "market_cap": 3_200_000_000_000,
            "volume": 24_000_000,
            "beta": 0.9,
            "dividend": None,
            "change_percent": 0.62,
        },
        {
            "symbol": "NVDA",
            "name": "NVIDIA Corp.",
            "sector": "Semiconductors",
            "industry": "AI Chips",
            "country": "US",
            "exchange": "NASDAQ",
            "price": 880.1,
            "market_cap": 2_200_000_000_000,
            "volume": 41_000_000,
            "beta": 1.7,
            "dividend": None,
            "change_percent": -0.8,
        },
        {
            "symbol": "AMZN",
            "name": "Amazon.com Inc.",
            "sector": "Consumer Discretionary",
            "industry": "Internet Retail",
            "country": "US",
            "exchange": "NASDAQ",
            "price": 184.7,
            "market_cap": 1_900_000_000_000,
            "volume": 36_000_000,
            "beta": 1.1,
            "dividend": None,
            "change_percent": 0.35,
        },
        {
            "symbol": "GOOGL",
            "name": "Alphabet Inc.",
            "sector": "Communication Services",
            "industry": "Internet Content",
            "country": "US",
            "exchange": "NASDAQ",
            "price": 175.4,
            "market_cap": 2_100_000_000_000,
            "volume": 28_000_000,
            "beta": 1.0,
            "dividend": None,
            "change_percent": 0.48,
        },
        {
            "symbol": "META",
            "name": "Meta Platforms Inc.",
            "sector": "Communication Services",
            "industry": "Social Media",
            "country": "US",
            "exchange": "NASDAQ",
            "price": 504.3,
            "market_cap": 1_280_000_000_000,
            "volume": 16_000_000,
            "beta": 1.3,
            "dividend": None,
            "change_percent": 0.74,
        },
    ],
    "CN": [
        {
            "symbol": "600519.SS",
            "name": "Kweichow Moutai Co., Ltd.",
            "sector": "Consumer Staples",
            "industry": "Beverages",
            "country": "CN",
            "exchange": "Shanghai",
            "price": 1702.0,
            "market_cap": 2_138_000_000_000,
            "volume": 2_100_000,
            "beta": 0.7,
            "dividend": None,
            "change_percent": 0.42,
        },
        {
            "symbol": "300750.SZ",
            "name": "Contemporary Amperex Technology Co., Ltd.",
            "sector": "Industrials",
            "industry": "Battery Manufacturing",
            "country": "CN",
            "exchange": "Shenzhen",
            "price": 193.6,
            "market_cap": 852_000_000_000,
            "volume": 15_200_000,
            "beta": 1.1,
            "dividend": None,
            "change_percent": -0.35,
        },
        {
            "symbol": "601318.SS",
            "name": "Ping An Insurance Group Co. of China, Ltd.",
            "sector": "Financials",
            "industry": "Insurance",
            "country": "CN",
            "exchange": "Shanghai",
            "price": 45.8,
            "market_cap": 812_000_000_000,
            "volume": 29_000_000,
            "beta": 0.9,
            "dividend": None,
            "change_percent": 0.18,
        },
        {
            "symbol": "000333.SZ",
            "name": "Midea Group Co., Ltd.",
            "sector": "Consumer Discretionary",
            "industry": "Home Appliances",
            "country": "CN",
            "exchange": "Shenzhen",
            "price": 70.4,
            "market_cap": 493_000_000_000,
            "volume": 18_500_000,
            "beta": 0.8,
            "dividend": None,
            "change_percent": 0.66,
        },
        {
            "symbol": "000858.SZ",
            "name": "Wuliangye Yibin Co., Ltd.",
            "sector": "Consumer Staples",
            "industry": "Beverages",
            "country": "CN",
            "exchange": "Shenzhen",
            "price": 132.5,
            "market_cap": 514_000_000_000,
            "volume": 11_400_000,
            "beta": 0.7,
            "dividend": None,
            "change_percent": -0.21,
        },
    ],
    "HK": [
        {
            "symbol": "0700.HK",
            "name": "Tencent Holdings Limited",
            "sector": "Communication Services",
            "industry": "Internet Content",
            "country": "HK",
            "exchange": "HKEX",
            "price": 381.0,
            "market_cap": 3_560_000_000_000,
            "volume": 20_800_000,
            "beta": 1.0,
            "dividend": None,
            "change_percent": 0.58,
        },
        {
            "symbol": "9988.HK",
            "name": "Alibaba Group Holding Limited",
            "sector": "Consumer Discretionary",
            "industry": "Internet Retail",
            "country": "HK",
            "exchange": "HKEX",
            "price": 81.2,
            "market_cap": 1_520_000_000_000,
            "volume": 73_000_000,
            "beta": 1.2,
            "dividend": None,
            "change_percent": 0.31,
        },
        {
            "symbol": "3690.HK",
            "name": "Meituan",
            "sector": "Consumer Discretionary",
            "industry": "Internet Services",
            "country": "HK",
            "exchange": "HKEX",
            "price": 118.6,
            "market_cap": 736_000_000_000,
            "volume": 45_000_000,
            "beta": 1.4,
            "dividend": None,
            "change_percent": -0.44,
        },
        {
            "symbol": "1299.HK",
            "name": "AIA Group Limited",
            "sector": "Financials",
            "industry": "Insurance",
            "country": "HK",
            "exchange": "HKEX",
            "price": 62.5,
            "market_cap": 683_000_000_000,
            "volume": 28_700_000,
            "beta": 0.8,
            "dividend": None,
            "change_percent": 0.14,
        },
        {
            "symbol": "1810.HK",
            "name": "Xiaomi Corporation",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "country": "HK",
            "exchange": "HKEX",
            "price": 18.9,
            "market_cap": 472_000_000_000,
            "volume": 91_000_000,
            "beta": 1.3,
            "dividend": None,
            "change_percent": 1.05,
        },
    ],
}

_STATIC_US_FALLBACK_ITEMS = _STATIC_FALLBACK_ITEMS["US"]

_POPULAR_TICKERS: dict[str, list[str]] = {
    "US": [
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B",
        "UNH", "JNJ", "V", "XOM", "JPM", "WMT", "PG", "MA", "HD", "CVX",
        "MRK", "ABBV", "LLY", "PFE", "KO", "PEP", "COST", "AVGO", "TMO",
        "MCD", "CSCO", "ACN", "ABT", "DHR", "NKE", "ORCL", "VZ", "ADBE",
    ],
    "CN": [
        "600519.SS", "300750.SZ", "601318.SS", "000333.SZ", "000858.SZ",
        "600036.SS", "601899.SS", "002594.SZ", "600276.SS", "601398.SS",
        "601288.SS", "000651.SZ", "600030.SS", "600900.SS", "601988.SS",
    ],
    "HK": [
        "0700.HK", "9988.HK", "3690.HK", "1299.HK", "1810.HK",
        "0939.HK", "1398.HK", "0005.HK", "0388.HK", "0883.HK",
        "2318.HK", "0941.HK", "1211.HK", "9618.HK", "1024.HK",
    ],
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
        response = _http_get(
            _ALPHA_TOP_MOVERS_URL,
            params={"function": "TOP_GAINERS_LOSERS", "apikey": ALPHA_VANTAGE_API_KEY},
            timeout=15,
        )
        if getattr(response, "status_code", 0) != 200:
            logger.info("Alpha Vantage top movers returned %s", getattr(response, "status_code", "unknown"))
            return None

        raw = response.json()
        if not isinstance(raw, dict) or raw.get("Information") or raw.get("Note"):
            logger.info("Alpha Vantage top movers unavailable: %s", raw.get("Information") or raw.get("Note"))
            return None

        rows = [
            *(raw.get("most_actively_traded") or []),
            *(raw.get("top_gainers") or []),
            *(raw.get("top_losers") or []),
        ]
        seen: set[str] = set()
        items: list[dict[str, Any]] = []
        active_filters = filters if isinstance(filters, dict) else {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("ticker") or "").strip().upper()
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)

            price = _clean_float(row.get("price"))
            volume = _clean_float(row.get("volume"))
            change_percent = _parse_percent(row.get("change_percentage"))
            if active_filters.get("priceMoreThan") and price and price < float(active_filters["priceMoreThan"]):
                continue
            if active_filters.get("priceLowerThan") and price and price > float(active_filters["priceLowerThan"]):
                continue
            if active_filters.get("volumeMoreThan") and volume and volume < float(active_filters["volumeMoreThan"]):
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
            "capability_note": "Using Alpha Vantage free top movers because FMP screener is not configured.",
        }
    except Exception as exc:
        logger.info("Alpha Vantage top movers fallback failed: %s", exc)
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

                # Apply filters
                if filters:
                    if filters.get("priceMoreThan") and price and price < float(filters["priceMoreThan"]):
                        continue
                    if filters.get("priceLowerThan") and price and price > float(filters["priceLowerThan"]):
                        continue
                    if filters.get("marketCapMoreThan") and market_cap and market_cap < float(filters["marketCapMoreThan"]):
                        continue
                    if filters.get("marketCapLowerThan") and market_cap and market_cap > float(filters["marketCapLowerThan"]):
                        continue
                    if filters.get("volumeMoreThan") and volume and volume < float(filters["volumeMoreThan"]):
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
                f"Using yfinance popular {market_norm} tickers because FMP screener is not configured."
                if is_live
                else "Using built-in market demo candidates because FMP/yfinance coverage is unavailable."
            ),
        }
    except Exception as exc:
        logger.warning("yfinance popular stocks failed: %s", exc)
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
                "capability_note": "Using built-in market demo candidates because FMP/yfinance data is unavailable.",
            }
        return {
            "success": False,
            "market": market,
            "items": [],
            "count": 0,
            "error": f"yfinance_fallback_failed: {exc}",
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
    max_live_probes = min(len(candidates), target_limit, 1)
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
            "capability_note": "CN/HK free quote data is temporarily slow or unavailable; try loosening filters.",
        }

    items = _sort_screener_items(items, sort_by, sort_order)
    sliced = items[:target_limit]
    live_count = sum(1 for item in sliced if item.get("_live"))
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
        "source": "eastmoney_quote" if live_count else "static_market_demo",
        "warning": "live_fallback_unavailable" if used_static_fallback and not live_count else None,
        "capability_note": (
            "Using Eastmoney free quote data for popular CN/HK tickers; built-in candidates fill any slow symbols."
            if live_count
            else "Using built-in market demo candidates because CN/HK free quote data is temporarily slow."
        ),
    }


def _passes_screener_filters(item: dict[str, Any], filters: dict[str, Any] | None) -> bool:
    active = filters if isinstance(filters, dict) else {}
    price = _clean_float(item.get("price"))
    market_cap = _clean_float(item.get("market_cap"))
    volume = _clean_float(item.get("volume"))
    if active.get("priceMoreThan") and price and price < float(active["priceMoreThan"]):
        return False
    if active.get("priceLowerThan") and price and price > float(active["priceLowerThan"]):
        return False
    if active.get("marketCapMoreThan") and market_cap and market_cap < float(active["marketCapMoreThan"]):
        return False
    if active.get("marketCapLowerThan") and market_cap and market_cap > float(active["marketCapLowerThan"]):
        return False
    if active.get("volumeMoreThan") and volume and volume < float(active["volumeMoreThan"]):
        return False
    return True


def _build_cn_hk_item(*, symbol: str, market: str, metrics: dict[str, Any]) -> dict[str, Any]:
    static_by_symbol = {
        str(item.get("symbol") or "").upper(): item
        for item in _STATIC_FALLBACK_ITEMS.get(market, [])
        if isinstance(item, dict)
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
        for item in _STATIC_FALLBACK_ITEMS.get(market, [])
        if isinstance(item, dict)
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
    for item in _STATIC_FALLBACK_ITEMS.get(market_norm, []):
        price = _clean_float(item.get("price"))
        market_cap = _clean_float(item.get("market_cap"))
        volume = _clean_float(item.get("volume"))
        if active_filters.get("priceMoreThan") and price and price < float(active_filters["priceMoreThan"]):
            continue
        if active_filters.get("priceLowerThan") and price and price > float(active_filters["priceLowerThan"]):
            continue
        if active_filters.get("marketCapMoreThan") and market_cap and market_cap < float(active_filters["marketCapMoreThan"]):
            continue
        if active_filters.get("marketCapLowerThan") and market_cap and market_cap > float(active_filters["marketCapLowerThan"]):
            continue
        if active_filters.get("volumeMoreThan") and volume and volume < float(active_filters["volumeMoreThan"]):
            continue
        items.append(dict(item))
    return items


def _static_us_fallback_items(filters: dict[str, Any] | None) -> list[dict[str, Any]]:
    return _static_fallback_items("US", filters)


def _clean_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _clean_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))


def _build_market_filters(market: str) -> dict[str, str]:
    m = str(market or "US").strip().upper()
    if m == "CN":
        return {"country": "CN"}
    if m == "HK":
        return {"exchange": "HKSE"}
    return {}


def screen_stocks(
    *,
    market: str = "US",
    filters: dict[str, Any] | None = None,
    limit: int = 20,
    page: int = 1,
    sort_by: str = "marketCap",
    sort_order: str = "desc",
) -> dict[str, Any]:
    """Run FMP stock screener with simple market-aware filters."""
    market_norm = str(market or "US").strip().upper()
    capability_note = None
    if market_norm in {"CN", "HK"}:
        capability_note = "CN/HK coverage is limited in FMP screener; empty or partial results are expected for some symbols."

    limit_norm = _clean_int(limit, default=20, minimum=1, maximum=200)
    page_norm = _clean_int(page, default=1, minimum=1, maximum=100)

    sort_key = str(sort_by or "marketCap").strip()
    if sort_key not in _ALLOWED_SORT_BY:
        sort_key = "marketCap"
    sort_dir = str(sort_order or "desc").strip().lower()
    if sort_dir not in _ALLOWED_SORT_ORDER:
        sort_dir = "desc"

    payload_filters = filters if isinstance(filters, dict) else {}

    if not FMP_API_KEY:
        logger.warning("FMP_API_KEY is not configured; using yfinance popular fallback")
        return _yfinance_screen_stocks(market_norm, payload_filters, limit_norm, sort_key, sort_dir)

    params: dict[str, Any] = {
        "apikey": FMP_API_KEY,
        "limit": limit_norm,
        "offset": (page_norm - 1) * limit_norm,
        "order": sort_dir,
        "sort": sort_key,
    }
    params.update(_build_market_filters(market))

    passthrough_keys = {
        "exchange",
        "country",
        "sector",
        "industry",
        "isEtf",
        "isActivelyTrading",
        "marketCapMoreThan",
        "marketCapLowerThan",
        "priceMoreThan",
        "priceLowerThan",
        "betaMoreThan",
        "betaLowerThan",
        "volumeMoreThan",
        "dividendMoreThan",
    }
    for key, value in payload_filters.items():
        if key not in passthrough_keys:
            continue
        if value is None or value == "":
            continue
        params[key] = value

    try:
        response = _http_get(_FMP_SCREENER_URL, params=params, timeout=15)
        if getattr(response, "status_code", 0) != 200:
            # FMP failed, try yfinance fallback
            logger.info("FMP screener returned %s, falling back to yfinance", getattr(response, "status_code", "unknown"))
            return _yfinance_screen_stocks(market_norm, payload_filters, limit_norm, sort_key, sort_dir)
        raw = response.json()
        # Check for FMP legacy endpoint error
        if isinstance(raw, dict) and "Error Message" in raw:
            logger.info("FMP legacy endpoint deprecated, falling back to yfinance")
            return _yfinance_screen_stocks(market_norm, payload_filters, limit_norm, sort_key, sort_dir)
        if not isinstance(raw, list):
            # Could be error response, fallback to yfinance
            logger.info("FMP returned non-list response, falling back to yfinance")
            return _yfinance_screen_stocks(market_norm, payload_filters, limit_norm, sort_key, sort_dir)

        items: list[dict[str, Any]] = []
        for row in raw:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            items.append(
                {
                    "symbol": symbol,
                    "name": str(row.get("companyName") or row.get("company") or "").strip() or symbol,
                    "sector": row.get("sector"),
                    "industry": row.get("industry"),
                    "country": row.get("country"),
                    "exchange": row.get("exchangeShortName") or row.get("exchange"),
                    "price": _clean_float(row.get("price")),
                    "market_cap": _clean_float(row.get("marketCap")),
                    "volume": _clean_float(row.get("volume")),
                    "beta": _clean_float(row.get("beta")),
                    "dividend": _clean_float(row.get("lastAnnualDividend")),
                    "change_percent": _clean_float(row.get("changesPercentage")),
                }
            )

        return {
            "success": True,
            "market": market_norm,
            "filters": payload_filters,
            "sort": {"by": sort_key, "order": sort_dir},
            "page": page_norm,
            "limit": limit_norm,
            "items": items,
            "count": len(items),
            "source": "fmp_stock_screener",
            "warning": None if items else ("coverage_limited_or_empty_result" if capability_note else "empty_result"),
            "capability_note": capability_note,
        }
    except Exception as exc:
        logger.warning("screen_stocks FMP failed: %s, trying yfinance fallback", exc)
        return _yfinance_screen_stocks(market_norm, payload_filters, limit_norm, sort_key, sort_dir)


__all__ = ["screen_stocks"]
