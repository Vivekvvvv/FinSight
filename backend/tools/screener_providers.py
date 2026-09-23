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

from backend.tools.env import ALPHA_VANTAGE_API_KEY
from backend.tools.http import _http_get
from backend.tools.cn_hk_market import fetch_cn_hk_quote_metrics
from backend.utils.quote import safe_float


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
        {
            "symbol": "TSLA",
            "name": "Tesla Inc.",
            "sector": "Consumer Discretionary",
            "industry": "Auto Manufacturers",
            "country": "US",
            "exchange": "NASDAQ",
            "price": 182.1,
            "market_cap": 580_000_000_000,
            "volume": 101_000_000,
            "beta": 2.1,
            "dividend": None,
            "change_percent": -1.12,
        },
        {
            "symbol": "BRK-B",
            "name": "Berkshire Hathaway Inc.",
            "sector": "Financials",
            "industry": "Insurance Diversified",
            "country": "US",
            "exchange": "NYSE",
            "price": 410.6,
            "market_cap": 890_000_000_000,
            "volume": 3_900_000,
            "beta": 0.9,
            "dividend": None,
            "change_percent": 0.16,
        },
        {
            "symbol": "LLY",
            "name": "Eli Lilly and Company",
            "sector": "Healthcare",
            "industry": "Drug Manufacturers",
            "country": "US",
            "exchange": "NYSE",
            "price": 872.4,
            "market_cap": 828_000_000_000,
            "volume": 3_100_000,
            "beta": 0.4,
            "dividend": 5.2,
            "change_percent": 0.38,
        },
        {
            "symbol": "AVGO",
            "name": "Broadcom Inc.",
            "sector": "Technology",
            "industry": "Semiconductors",
            "country": "US",
            "exchange": "NASDAQ",
            "price": 1410.2,
            "market_cap": 656_000_000_000,
            "volume": 2_700_000,
            "beta": 1.2,
            "dividend": 21.0,
            "change_percent": 0.91,
        },
        {
            "symbol": "JPM",
            "name": "JPMorgan Chase & Co.",
            "sector": "Financials",
            "industry": "Banks Diversified",
            "country": "US",
            "exchange": "NYSE",
            "price": 198.7,
            "market_cap": 571_000_000_000,
            "volume": 8_800_000,
            "beta": 1.1,
            "dividend": 4.6,
            "change_percent": 0.22,
        },
        {
            "symbol": "V",
            "name": "Visa Inc.",
            "sector": "Financials",
            "industry": "Credit Services",
            "country": "US",
            "exchange": "NYSE",
            "price": 278.9,
            "market_cap": 560_000_000_000,
            "volume": 6_100_000,
            "beta": 0.9,
            "dividend": 2.1,
            "change_percent": 0.44,
        },
        {
            "symbol": "UNH",
            "name": "UnitedHealth Group Inc.",
            "sector": "Healthcare",
            "industry": "Healthcare Plans",
            "country": "US",
            "exchange": "NYSE",
            "price": 512.8,
            "market_cap": 472_000_000_000,
            "volume": 3_800_000,
            "beta": 0.6,
            "dividend": 7.5,
            "change_percent": -0.18,
        },
        {
            "symbol": "XOM",
            "name": "Exxon Mobil Corporation",
            "sector": "Energy",
            "industry": "Oil & Gas Integrated",
            "country": "US",
            "exchange": "NYSE",
            "price": 113.4,
            "market_cap": 452_000_000_000,
            "volume": 17_500_000,
            "beta": 1.0,
            "dividend": 3.8,
            "change_percent": 0.27,
        },
        {
            "symbol": "WMT",
            "name": "Walmart Inc.",
            "sector": "Consumer Staples",
            "industry": "Discount Stores",
            "country": "US",
            "exchange": "NYSE",
            "price": 67.3,
            "market_cap": 541_000_000_000,
            "volume": 14_400_000,
            "beta": 0.5,
            "dividend": 0.8,
            "change_percent": 0.19,
        },
        {
            "symbol": "MA",
            "name": "Mastercard Incorporated",
            "sector": "Financials",
            "industry": "Credit Services",
            "country": "US",
            "exchange": "NYSE",
            "price": 452.6,
            "market_cap": 421_000_000_000,
            "volume": 2_500_000,
            "beta": 1.0,
            "dividend": 2.6,
            "change_percent": 0.51,
        },
        {
            "symbol": "PG",
            "name": "Procter & Gamble Company",
            "sector": "Consumer Staples",
            "industry": "Household & Personal Products",
            "country": "US",
            "exchange": "NYSE",
            "price": 166.2,
            "market_cap": 392_000_000_000,
            "volume": 6_900_000,
            "beta": 0.4,
            "dividend": 4.0,
            "change_percent": -0.08,
        },
        {
            "symbol": "JNJ",
            "name": "Johnson & Johnson",
            "sector": "Healthcare",
            "industry": "Drug Manufacturers",
            "country": "US",
            "exchange": "NYSE",
            "price": 148.9,
            "market_cap": 358_000_000_000,
            "volume": 7_600_000,
            "beta": 0.5,
            "dividend": 4.8,
            "change_percent": 0.12,
        },
        {
            "symbol": "HD",
            "name": "The Home Depot Inc.",
            "sector": "Consumer Discretionary",
            "industry": "Home Improvement Retail",
            "country": "US",
            "exchange": "NYSE",
            "price": 348.5,
            "market_cap": 346_000_000_000,
            "volume": 3_400_000,
            "beta": 1.0,
            "dividend": 8.4,
            "change_percent": -0.25,
        },
        {
            "symbol": "COST",
            "name": "Costco Wholesale Corporation",
            "sector": "Consumer Staples",
            "industry": "Discount Stores",
            "country": "US",
            "exchange": "NASDAQ",
            "price": 812.3,
            "market_cap": 360_000_000_000,
            "volume": 2_100_000,
            "beta": 0.8,
            "dividend": 4.6,
            "change_percent": 0.33,
        },
        {
            "symbol": "ORCL",
            "name": "Oracle Corporation",
            "sector": "Technology",
            "industry": "Software Infrastructure",
            "country": "US",
            "exchange": "NYSE",
            "price": 125.7,
            "market_cap": 346_000_000_000,
            "volume": 8_200_000,
            "beta": 1.0,
            "dividend": 1.6,
            "change_percent": 0.68,
        },
        {
            "symbol": "MRK",
            "name": "Merck & Co., Inc.",
            "sector": "Healthcare",
            "industry": "Drug Manufacturers",
            "country": "US",
            "exchange": "NYSE",
            "price": 127.2,
            "market_cap": 322_000_000_000,
            "volume": 8_700_000,
            "beta": 0.4,
            "dividend": 3.1,
            "change_percent": 0.06,
        },
        {
            "symbol": "ABBV",
            "name": "AbbVie Inc.",
            "sector": "Healthcare",
            "industry": "Drug Manufacturers",
            "country": "US",
            "exchange": "NYSE",
            "price": 164.8,
            "market_cap": 291_000_000_000,
            "volume": 5_500_000,
            "beta": 0.6,
            "dividend": 6.2,
            "change_percent": -0.14,
        },
        {
            "symbol": "CVX",
            "name": "Chevron Corporation",
            "sector": "Energy",
            "industry": "Oil & Gas Integrated",
            "country": "US",
            "exchange": "NYSE",
            "price": 156.9,
            "market_cap": 289_000_000_000,
            "volume": 7_900_000,
            "beta": 1.1,
            "dividend": 6.5,
            "change_percent": 0.21,
        },
        {
            "symbol": "KO",
            "name": "The Coca-Cola Company",
            "sector": "Consumer Staples",
            "industry": "Beverages",
            "country": "US",
            "exchange": "NYSE",
            "price": 62.4,
            "market_cap": 269_000_000_000,
            "volume": 13_100_000,
            "beta": 0.6,
            "dividend": 1.9,
            "change_percent": 0.09,
        },
        {
            "symbol": "PEP",
            "name": "PepsiCo Inc.",
            "sector": "Consumer Staples",
            "industry": "Beverages",
            "country": "US",
            "exchange": "NASDAQ",
            "price": 172.5,
            "market_cap": 237_000_000_000,
            "volume": 5_200_000,
            "beta": 0.5,
            "dividend": 5.1,
            "change_percent": -0.05,
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
        "601857.SS", "601088.SS", "600028.SS", "601166.SS", "600887.SS",
        "601668.SS", "600309.SS", "002415.SZ", "000725.SZ", "601012.SS",
        "600406.SS", "002475.SZ", "300059.SZ", "600050.SS", "601919.SS",
    ],
    "HK": [
        "0700.HK", "9988.HK", "3690.HK", "1299.HK", "1810.HK",
        "0939.HK", "1398.HK", "0005.HK", "0388.HK", "0883.HK",
        "2318.HK", "0941.HK", "1211.HK", "9618.HK", "1024.HK",
        "9999.HK", "2020.HK", "2331.HK", "2388.HK", "1109.HK",
        "0823.HK", "2628.HK", "3968.HK", "2269.HK", "6690.HK",
        "9866.HK", "9888.HK", "2015.HK", "9992.HK", "1928.HK",
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
