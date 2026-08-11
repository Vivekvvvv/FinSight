from __future__ import annotations

import logging
import time
from typing import Any


from backend.tools.env import FMP_API_KEY
from backend.tools.http import _http_get
from backend.tools.us_screener import nasdaq_screen_stocks

logger = logging.getLogger(__name__)

from backend.tools.screener_providers import (
    _ALPHA_TOP_MOVERS_URL,
    _ALPHA_TOP_MOVERS_CACHE,
    _ALPHA_TOP_MOVERS_TTL_SECONDS,
    _CN_HK_LIVE_UNAVAILABLE_UNTIL,
    _CN_HK_LIVE_COOLDOWN_SECONDS,
    _YF_SCREENER_MAP,
    _STATIC_FALLBACK_ITEMS,
    _STATIC_US_FALLBACK_ITEMS,
    _POPULAR_TICKERS,
    _yfinance_screen_stocks,
    _static_screen_stocks,
    _parse_percent,
    _alpha_vantage_screen_stocks,
    _yfinance_popular_stocks,
    _cn_hk_popular_stocks,
    _passes_screener_filters,
    _build_cn_hk_item,
    _get_fast_info_value,
    _build_yfinance_item,
    _sort_screener_items,
    _static_fallback_items,
    _static_us_fallback_items,
    _clean_float,
)


_FMP_SCREENER_URL = "https://financialmodelingprep.com/stable/company-screener"
_ALLOWED_SORT_BY = {
    "marketCap",
    "price",
    "volume",
    "beta",
    "lastAnnualDividend",
    "changesPercentage",
}
_ALLOWED_SORT_ORDER = {"asc", "desc"}
_FMP_SCREENER_UNAVAILABLE_UNTIL = 0.0
_FMP_SCREENER_UNAVAILABLE_STATUS: int | None = None
_FMP_SCREENER_COOLDOWN_SECONDS = 300

# Yahoo Finance predefined screener keys by market


_FALLBACK_COMPANY_NAMES: dict[str, str] = {
    "PFE": "Pfizer Inc.",
    "TMO": "Thermo Fisher Scientific Inc.",
    "MCD": "McDonald's Corporation",
    "CSCO": "Cisco Systems, Inc.",
    "ACN": "Accenture plc",
    "ABT": "Abbott Laboratories",
    "DHR": "Danaher Corporation",
    "NKE": "NIKE, Inc.",
    "VZ": "Verizon Communications Inc.",
    "ADBE": "Adobe Inc.",
    "600036.SS": "China Merchants Bank Co., Ltd.",
    "601899.SS": "Zijin Mining Group Co., Ltd.",
    "002594.SZ": "BYD Company Limited",
    "600276.SS": "Jiangsu Hengrui Pharmaceuticals Co., Ltd.",
    "601398.SS": "Industrial and Commercial Bank of China Limited",
    "601288.SS": "Agricultural Bank of China Limited",
    "000651.SZ": "Gree Electric Appliances, Inc.",
    "600030.SS": "CITIC Securities Company Limited",
    "600900.SS": "China Yangtze Power Co., Ltd.",
    "601988.SS": "Bank of China Limited",
    "601857.SS": "PetroChina Company Limited",
    "601088.SS": "China Shenhua Energy Company Limited",
    "600028.SS": "China Petroleum & Chemical Corporation",
    "601166.SS": "Industrial Bank Co., Ltd.",
    "600887.SS": "Inner Mongolia Yili Industrial Group Co., Ltd.",
    "601668.SS": "China State Construction Engineering Corporation Limited",
    "600309.SS": "Wanhua Chemical Group Co., Ltd.",
    "002415.SZ": "Hangzhou Hikvision Digital Technology Co., Ltd.",
    "000725.SZ": "BOE Technology Group Co., Ltd.",
    "601012.SS": "LONGi Green Energy Technology Co., Ltd.",
    "600406.SS": "NARI Technology Co., Ltd.",
    "002475.SZ": "Luxshare Precision Industry Co., Ltd.",
    "300059.SZ": "East Money Information Co., Ltd.",
    "600050.SS": "China United Network Communications Limited",
    "601919.SS": "COSCO Shipping Holdings Co., Ltd.",
    "0939.HK": "China Construction Bank Corporation",
    "1398.HK": "Industrial and Commercial Bank of China Limited",
    "0005.HK": "HSBC Holdings plc",
    "0388.HK": "Hong Kong Exchanges and Clearing Limited",
    "0883.HK": "CNOOC Limited",
    "2318.HK": "Ping An Insurance Group Co. of China, Ltd.",
    "0941.HK": "China Mobile Limited",
    "1211.HK": "BYD Company Limited",
    "9618.HK": "JD.com, Inc.",
    "1024.HK": "Kuaishou Technology",
    "9999.HK": "NetEase, Inc.",
    "2020.HK": "ANTA Sports Products Limited",
    "2331.HK": "Li Ning Company Limited",
    "2388.HK": "BOC Hong Kong (Holdings) Limited",
    "1109.HK": "China Resources Land Limited",
    "0823.HK": "Link Real Estate Investment Trust",
    "2628.HK": "China Life Insurance Company Limited",
    "3968.HK": "China Merchants Bank Co., Ltd.",
    "2269.HK": "WuXi Biologics (Cayman) Inc.",
    "6690.HK": "Haier Smart Home Co., Ltd.",
    "9866.HK": "NIO Inc.",
    "9888.HK": "Baidu, Inc.",
    "2015.HK": "Li Auto Inc.",
    "9992.HK": "Pop Mart International Group Limited",
    "1928.HK": "Sands China Ltd.",
}

_FALLBACK_SECTOR_BY_MARKET: dict[str, list[tuple[str, str]]] = {
    "US": [
        ("Technology", "Software & Services"),
        ("Healthcare", "Healthcare & Life Sciences"),
        ("Consumer Discretionary", "Consumer Products"),
        ("Communication Services", "Telecom & Media"),
        ("Industrials", "Industrial Products"),
    ],
    "CN": [
        ("Financials", "Banks"),
        ("Materials", "Metals & Mining"),
        ("Consumer Discretionary", "Auto Manufacturers"),
        ("Healthcare", "Pharmaceuticals"),
        ("Utilities", "Electric Utilities"),
    ],
    "HK": [
        ("Financials", "Banks"),
        ("Energy", "Oil & Gas"),
        ("Communication Services", "Telecom Services"),
        ("Consumer Discretionary", "Internet Retail"),
        ("Technology", "Internet Services"),
    ],
}


def _ensure_static_fallback_coverage() -> None:
    for market in ("US", "CN", "HK"):
        items = _STATIC_FALLBACK_ITEMS.setdefault(market, [])
        seen = {str(item.get("symbol") or "").upper() for item in items}
        sector_cycle = _FALLBACK_SECTOR_BY_MARKET[market]
        for index, symbol in enumerate(_POPULAR_TICKERS.get(market, [])):
            if symbol in seen:
                continue
            sector, industry = sector_cycle[index % len(sector_cycle)]
            market_cap = max(80_000_000_000, 450_000_000_000 - index * 18_000_000_000)
            items.append({
                "symbol": symbol,
                "name": _FALLBACK_COMPANY_NAMES.get(symbol, symbol),
                "sector": sector,
                "industry": industry,
                "country": market,
                "exchange": "HKEX" if market == "HK" else ("Shanghai" if symbol.endswith(".SS") else "Shenzhen"),
                "price": round(20 + index * 3.7, 2),
                "market_cap": market_cap,
                "volume": 5_000_000 + index * 1_250_000,
                "beta": round(0.7 + (index % 5) * 0.1, 1),
                "dividend": None,
                "change_percent": round((index % 7 - 3) * 0.18, 2),
            })
            seen.add(symbol)


_ensure_static_fallback_coverage()


def _with_fmp_fallback_note(result: dict[str, Any], *, status_code: int | None = None) -> dict[str, Any]:
    """Attach a user-facing reason when FMP's paid screener cannot be used."""
    note = (
        "当前 FMP key 不支持批量筛选接口"
        + (f"（HTTP {status_code}）" if status_code else "")
        + "，已切换到免费数据源或内置候选池。"
    )
    merged = dict(result)
    existing = str(merged.get("capability_note") or "").strip()
    merged["capability_note"] = f"{note} {existing}".strip()
    merged["warning"] = merged.get("warning") or "fmp_screener_unavailable"
    return merged


def _remember_fmp_screener_unavailable(status_code: int | None) -> None:
    global _FMP_SCREENER_UNAVAILABLE_STATUS, _FMP_SCREENER_UNAVAILABLE_UNTIL
    if status_code not in {402, 403}:
        return
    _FMP_SCREENER_UNAVAILABLE_STATUS = status_code
    _FMP_SCREENER_UNAVAILABLE_UNTIL = time.monotonic() + _FMP_SCREENER_COOLDOWN_SECONDS


def _fmp_screener_unavailable_status() -> int | None:
    if time.monotonic() >= _FMP_SCREENER_UNAVAILABLE_UNTIL:
        return None
    return _FMP_SCREENER_UNAVAILABLE_STATUS


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

    if market_norm in {"CN", "HK"}:
        # 全市场真实数据（东财免 key，A股 5000+/港股主板）优先；
        # 上游故障返回 None 时回落既有链（Alpha Vantage/yfinance 15 只热门票/静态演示）
        from backend.tools.cn_screener import eastmoney_screen_stocks

        em_result = eastmoney_screen_stocks(
            market=market_norm,
            filters=payload_filters,
            limit=limit_norm,
            page=page_norm,
            sort_by=sort_key,
            sort_order=sort_dir,
        )
        if em_result is not None:
            return em_result
        return _yfinance_screen_stocks(market_norm, payload_filters, limit_norm, sort_key, sort_dir)

    if not FMP_API_KEY:
        logger.warning("FMP_API_KEY is not configured; using free market sources")
        if market_norm == "US":
            public_result = nasdaq_screen_stocks(
                filters=payload_filters,
                limit=limit_norm,
                page=page_norm,
                sort_by=sort_key,
                sort_order=sort_dir,
            )
            if public_result is not None:
                return public_result
            return _static_screen_stocks(market_norm, payload_filters, limit_norm, sort_key, sort_dir)
        return _yfinance_screen_stocks(market_norm, payload_filters, limit_norm, sort_key, sort_dir)

    unavailable_status = _fmp_screener_unavailable_status()
    if unavailable_status:
        logger.info("FMP screener is in cooldown; using free sources")
        return _with_fmp_fallback_note(
            _yfinance_screen_stocks(market_norm, payload_filters, limit_norm, sort_key, sort_dir),
            status_code=unavailable_status,
        )

    params: dict[str, Any] = {
        "apikey": FMP_API_KEY,
        "limit": limit_norm,
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
            status_code = getattr(response, "status_code", None)
            logger.info("FMP screener returned a non-success status; falling back to free sources")
            _remember_fmp_screener_unavailable(status_code)
            return _with_fmp_fallback_note(
                _yfinance_screen_stocks(market_norm, payload_filters, limit_norm, sort_key, sort_dir),
                status_code=status_code,
            )
        raw = response.json()
        # Check for FMP legacy endpoint error
        if isinstance(raw, dict) and "Error Message" in raw:
            logger.info("FMP screener returned an error payload, falling back to free sources")
            return _with_fmp_fallback_note(_yfinance_screen_stocks(market_norm, payload_filters, limit_norm, sort_key, sort_dir))
        if not isinstance(raw, list):
            logger.info("FMP returned non-list response, falling back to free sources")
            return _with_fmp_fallback_note(_yfinance_screen_stocks(market_norm, payload_filters, limit_norm, sort_key, sort_dir))

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
                    "name": str(row.get("companyName") or row.get("company") or row.get("companyName") or row.get("name") or "").strip() or symbol,
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

        items = _sort_screener_items(items, sort_key, sort_dir)
        offset = (page_norm - 1) * limit_norm
        sliced = items[offset:offset + limit_norm]
        return {
            "success": True,
            "market": market_norm,
            "filters": payload_filters,
            "sort": {"by": sort_key, "order": sort_dir},
            "page": page_norm,
            "limit": limit_norm,
            "items": sliced,
            "results": sliced,
            "count": len(sliced),
            "source": "fmp_company_screener",
            "warning": None if sliced else ("coverage_limited_or_empty_result" if capability_note else "empty_result"),
            "capability_note": capability_note,
        }
    except Exception as exc:
        logger.warning(
            "screen_stocks FMP failed: %s, trying free-source fallback",
            type(exc).__name__,
        )
        return _with_fmp_fallback_note(_yfinance_screen_stocks(market_norm, payload_filters, limit_norm, sort_key, sort_dir))


__all__ = ["screen_stocks"]
