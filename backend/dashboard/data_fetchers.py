# -*- coding: utf-8 -*-
"""Market/snapshot/news data retrieval helpers extracted from data_service.py (round 19)."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

from backend.utils.quote import safe_float
from backend.tools._item import iter_dict_items

from backend.dashboard.news_ranking import (
    _empty_news_payload,
    _news_ranking_meta,
    _parse_news_text,
    _rank_news_items,
    _to_news_item,
    _ts_seconds,
    _unique_news_items,
)

logger = logging.getLogger(__name__)


_FEAR_GREED_PATTERN = re.compile(
    r"(?:fear\s*&?\s*greed(?:\s*index)?|恐惧贪婪指数)[^0-9+-]{0,20}([+-]?[0-9]+(?:\.\d+)?)",
    re.IGNORECASE,
)


def _label_fear_greed(value: float) -> str:
    parsed = safe_float(value)
    score = 50.0 if parsed is None else max(0.0, min(100.0, parsed))
    if score <= 20:
        return "extreme_fear"
    if score <= 40:
        return "fear"
    if score <= 60:
        return "neutral"
    if score <= 80:
        return "greed"
    return "extreme_greed"


def _parse_fear_greed_value(text: str) -> Optional[float]:
    if not isinstance(text, str) or not text.strip():
        return None
    m = _FEAR_GREED_PATTERN.search(text)
    if not m:
        return None
    try:
        value = float(m.group(1))
    except Exception:
        return None
    return value if 0 <= value <= 100 else None


def fetch_macro_snapshot() -> dict[str, Any]:
    """
    Build a lightweight macro snapshot for dashboard first paint.

    Data sources:
    - get_market_sentiment(): CNN Fear & Greed text
    - get_fred_data(): macro fundamentals (rates, CPI, unemployment, etc.)
    """
    snapshot: dict[str, Any] = {
        "fear_greed_index": None,
        "fear_greed_label": "",
        "sentiment_text": "",
        "fed_rate": None,
        "cpi": None,
        "unemployment": None,
        "gdp_growth": None,
        "treasury_10y": None,
        "yield_spread": None,
        "source": "macro_tools",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "status": "unavailable",
    }

    has_fear_greed = False
    has_fred = False

    try:
        from backend.tools.macro import get_market_sentiment

        sentiment_text = str(get_market_sentiment() or "").strip()
        if sentiment_text:
            snapshot["sentiment_text"] = sentiment_text
            fear_greed_value = _parse_fear_greed_value(sentiment_text)
            if fear_greed_value is not None:
                snapshot["fear_greed_index"] = fear_greed_value
                snapshot["fear_greed_label"] = _label_fear_greed(fear_greed_value)
                has_fear_greed = True
    except Exception as exc:
        logger.warning("[DataService] fetch_macro_snapshot sentiment failed")

    try:
        from backend.tools.macro import get_fred_data

        fred_payload = get_fred_data()
        if (isinstance(fred_payload, dict) and not fred_payload.get("error") and fred_payload.get("success") is not False
            and str(fred_payload.get("status") or "").strip().lower() not in {"error", "failed", "unavailable"}):
            for key in ("fed_rate", "cpi", "unemployment", "gdp_growth", "treasury_10y", "yield_spread"):
                value = safe_float(fred_payload.get(key))
                if key == "unemployment" and value is not None and not 0 <= value <= 100:
                    continue
                if value is not None:
                    snapshot[key] = value
                    has_fred = True
            fred_as_of = str(fred_payload.get("as_of") or "").strip()
            if fred_as_of:
                snapshot["as_of"] = fred_as_of
    except Exception as exc:
        logger.warning("[DataService] fetch_macro_snapshot FRED failed")

    if has_fear_greed and has_fred:
        snapshot["status"] = "ok"
    elif has_fear_greed or has_fred:
        snapshot["status"] = "partial"

    return snapshot


def _parse_time_to_unix(time_value: Any) -> Optional[int]:
    return _ts_seconds(time_value)


def fetch_market_chart(symbol: str, period: str = "1y", interval: str = "1d") -> list[dict[str, Any]] | None:
    """Return OHLCV list for charting, or ``None`` on fetch failure.

    Returning ``None`` (not ``[]``) on failure ensures the caller does NOT
    cache an empty result as valid data.
    """
    try:
        hist = _load_ohlcv_frame(symbol, period=period, interval=interval)
        if hist is None or hist.empty:
            return None  # fetch failure — do not cache as valid
        required_columns = {"Open", "High", "Low", "Close"}
        if not required_columns.issubset(set(hist.columns)):
            return None  # bad data — do not cache as valid
        output: list[dict[str, Any]] = []
        for ts_index, row in hist.iterrows():
            if ((isinstance(row.get("error"), str) and row["error"].strip()) or row.get("success") is False
                or str(row.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
                continue
            if any(value is not None and not (isinstance(value, float) and pd.isna(value))
                   and str(value).strip().upper() != symbol.strip().upper()
                   for value in (row.get("ticker"), row.get("symbol"))):
                continue
            ts = _parse_time_to_unix(ts_index)
            if ts is None:
                continue
            if any((value := safe_float(row.get(field))) is None or value <= 0
                   for field in ("Open", "High", "Low", "Close")):
                continue
            if (safe_float(row.get("Low")) > min(safe_float(row.get("Open")), safe_float(row.get("Close")))
                or safe_float(row.get("High")) < max(safe_float(row.get("Open")), safe_float(row.get("Close")))):
                continue
            output.append(
                {
                    "time": ts,
                    "open": safe_float(row.get("Open")),
                    "high": safe_float(row.get("High")),
                    "low": safe_float(row.get("Low")),
                    "close": safe_float(row.get("Close")),
                    "volume": max(0.0, safe_float(row.get("Volume")) or 0.0),
                }
            )
        output = list({item["time"]: item for item in output}.values())
        output.sort(key=lambda item: item["time"])
        return output if output else None
    except Exception as exc:
        logger.warning("[DataService] fetch_market_chart failed")
        return None  # exception — do not cache


def fetch_snapshot(symbol: str, asset_type: str) -> dict[str, Any] | None:
    """Return snapshot dict, or ``None`` on fetch failure."""
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        info: dict[str, Any] = {}
        try:
            info = getattr(ticker, "info", {}) or {}
        except Exception:
            if asset_type == "equity":
                return None
            info = {}

        if (not isinstance(info, dict) or info.get("error") or info.get("success") is False
            or str(info.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
            return None
        if any(value is not None and str(value).strip().upper() != symbol.strip().upper()
               for value in (info.get("ticker"), info.get("symbol"))):
            return None
        last_close = None
        try:
            hist = ticker.history(period="5d", interval="1d")
            if hist is not None and not hist.empty:
                last_close = safe_float(hist["Close"].iloc[-1])
                if last_close is not None and last_close <= 0:
                    last_close = None
        except Exception:
            last_close = None

        output: dict[str, Any] = {}
        if asset_type == "equity":
            output.update(
                {
                    "revenue": safe_float(info.get("totalRevenue")),
                    # trailingEps=0.0（盈亏平衡）是真实值，裸 `or` 会把它当缺失、
                    # 用 forwardEps（预测值）顶替——显式 None 判断，只在缺失时回退。
                    "eps": next((value for value in (safe_float(info.get("trailingEps")), safe_float(info.get("forwardEps")))
                                 if value is not None), None),
                    "gross_margin": safe_float(info.get("grossMargins")),
                    "fcf": safe_float(info.get("freeCashflow")),
                }
            )
        elif asset_type in {"index", "crypto"}:
            if last_close is not None:
                output["index_level"] = last_close
        elif asset_type == "etf":
            nav = safe_float(info.get("navPrice"))
            output["nav"] = nav if nav is not None and nav > 0 else last_close

        return output
    except Exception as exc:
        logger.warning("[DataService] fetch_snapshot failed")
        return None  # failure — do not cache


def fetch_revenue_trend(symbol: str) -> list[dict[str, Any]] | None:
    """Return revenue-trend rows, or ``None`` on fetch failure.

    ``[]`` means "upstream has no revenue data for this asset" and is valid,
    cacheable data; ``None`` means the fetch itself failed. The caller
    (dashboard_router) only treats ``None`` as failure, so collapsing the two
    makes a transient outage cache as "this company has no revenue".
    """
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        financials = getattr(ticker, "quarterly_income_stmt", None)
        if financials is None or (hasattr(financials, "empty") and financials.empty):
            financials = getattr(ticker, "quarterly_financials", None)
        if financials is None or (hasattr(financials, "empty") and financials.empty):
            return []

        revenue_row = None
        for key in ("Total Revenue", "Revenue", "Net Sales", "Operating Revenue"):
            if key in financials.index:
                revenue_row = financials.loc[key]
                break
        if revenue_row is None:
            return []

        output: list[dict[str, Any]] = []
        for col in revenue_row.index:
            value = safe_float(revenue_row[col])
            if value is None:
                continue
            if isinstance(col, pd.Timestamp):
                period = f"{col.year} Q{(col.month - 1) // 3 + 1}"
            else:
                period = str(col)[:10]
            output.append({"period": period, "value": value, "name": period})

        output.sort(key=lambda row: row["period"])
        return output[-8:]
    except Exception as exc:
        logger.warning("[DataService] fetch_revenue_trend failed")
        return None  # exception — do not cache as valid


def fetch_segment_mix(symbol: str) -> list[dict[str, Any]] | None:
    """Return segment-mix rows, or ``None`` on fetch failure (see fetch_revenue_trend)."""
    try:
        from backend.tools.fmp import get_revenue_product_segmentation

        rows = get_revenue_product_segmentation(symbol)
        if not rows:
            return []
        return [
            {
                "name": row["segment"].strip(),
                "value": revenue,
                "weight": percentage / 100,
            }
            for row in iter_dict_items(rows)
            if isinstance(row.get("segment"), str) and row["segment"].strip()
            and (revenue := safe_float(row.get("revenue"))) is not None and revenue >= 0
            and (percentage := safe_float(row.get("percentage"))) is not None and 0 <= percentage <= 100
            and not row.get("error") and row.get("success") is not False
            and str(row.get("status") or "").strip().lower() not in {"error", "failed", "unavailable"}
            and all(value is None or isinstance(value, str) and value.strip().upper() == symbol.strip().upper()
                    for value in (row.get("ticker"), row.get("symbol")))
        ]
    except Exception as exc:
        logger.warning("[DataService] fetch_segment_mix failed")
        return None  # exception — do not cache as valid


def fetch_news(symbol: str, limit: int = 20) -> dict[str, Any] | None:
    if limit <= 0:
        return _empty_news_payload()
    try:
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
        from backend.tools.news import get_company_news, get_market_news_headlines

        impact_items: list[Any] = []
        market_items: list[Any] = []
        impact_ok = False
        market_ok = False

        # Parallel fetch: company news + market headlines
        # 不用 with：__exit__ 的 shutdown(wait=True) 会阻塞到仍在跑的慢源
        # 返回，result(timeout=30) 的延迟预算被架空。显式 wait=False +
        # cancel_futures 让超时路径按预算返回（线程收尾靠源自身超时）。
        pool = ThreadPoolExecutor(max_workers=2)
        try:
            f_impact = pool.submit(get_company_news, symbol, limit)
            f_market = pool.submit(get_market_news_headlines, limit)

            try:
                raw_impact = f_impact.result(timeout=30)
                if isinstance(raw_impact, list):
                    impact_items = raw_impact
                    impact_ok = True
                elif isinstance(raw_impact, str):
                    impact_items = _parse_news_text(raw_impact)
                    impact_ok = True
            except (FuturesTimeout, Exception) as exc:
                logger.warning("[DataService] get_company_news failed")

            try:
                raw_market = f_market.result(timeout=30)
                if isinstance(raw_market, list):
                    market_items = raw_market
                    market_ok = True
                elif isinstance(raw_market, str):
                    market_items = _parse_news_text(raw_market)
                    market_ok = True
            except (FuturesTimeout, Exception) as exc:
                logger.warning("[DataService] get_market_news_headlines failed")
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

        # 两个来源都抛异常（而非都返回空列表）→ 视为 news 管道故障，返回 None。
        # 此前无论如何都返回空 payload，而 router 只把 None 当失败，导致真实
        # 故障被当成"高置信度无新闻"、缓存 TTL_NEWS 时长且不标 fallback（R51）。
        if not impact_ok and not market_ok:
            return None

        market_raw = _unique_news_items([normalized for item in market_items if (normalized := _to_news_item(item))["title"]])
        impact_raw = _unique_news_items([normalized for item in impact_items if (normalized := _to_news_item(item))["title"]])
        if not market_raw and not impact_raw and (market_items or impact_items):
            logger.warning("[DataService] news rows unusable")
            return None

        result = {
            "market": _rank_news_items(market_raw, limit, symbol=symbol, mode="market"),
            "impact": _rank_news_items(impact_raw, limit, symbol=symbol, mode="impact"),
            "market_raw": market_raw[:limit],
            "impact_raw": impact_raw[:limit],
            "ranking_meta": _news_ranking_meta(),
        }
        return result
    except Exception as exc:
        logger.warning("[DataService] fetch_news failed")
        return None


def fetch_sector_weights(symbol: str, asset_type: str) -> list[dict[str, Any]] | None:
    """Return sector weights, or ``None`` on fetch failure (see fetch_revenue_trend)."""
    if asset_type not in {"etf", "index"}:
        return []  # not applicable for this asset type — valid empty
    try:
        from backend.tools.fmp import get_etf_sector_weights

        rows = get_etf_sector_weights(symbol)
        if not rows:
            return []
        return [
            {"name": row["sector"].strip(), "weight": weight / 100}
            for row in iter_dict_items(rows)
            if isinstance(row.get("sector"), str) and row["sector"].strip()
            and (weight := safe_float(row.get("weight"))) is not None and 0 <= weight <= 100
            and not row.get("error") and row.get("success") is not False
            and str(row.get("status") or "").strip().lower() not in {"error", "failed", "unavailable"}
        ]
    except Exception as exc:
        logger.warning("[DataService] fetch_sector_weights failed")
        return None  # exception — do not cache as valid


def fetch_top_constituents(symbol: str, asset_type: str, limit: int = 10) -> list[dict[str, Any]] | None:
    """Return index constituents, or ``None`` on fetch failure (see fetch_revenue_trend)."""
    if asset_type != "index" or limit <= 0:
        return []  # not applicable for this asset type — valid empty
    try:
        from backend.tools.fmp import get_index_constituents

        rows = get_index_constituents(symbol)
        if not rows:
            return []
        return [
            {
                "symbol": row["symbol"].strip().upper(),
                "name": row["name"].strip() if isinstance(row.get("name"), str) and row["name"].strip() else row["symbol"].strip().upper(),
                "weight": weight if (weight := safe_float(row.get("weight"))) is not None and 0 <= weight <= 100 else 0.0,
            }
            for row in [r for r in iter_dict_items(rows)
                        if isinstance(r.get("symbol"), str) and r["symbol"].strip()
                        and not r.get("error") and r.get("success") is not False
                        and str(r.get("status") or "").strip().lower() not in {"error", "failed", "unavailable"}][:limit]
        ]
    except Exception as exc:
        logger.warning("[DataService] fetch_top_constituents failed")
        return None  # exception — do not cache as valid


def fetch_holdings(symbol: str, asset_type: str, limit: int = 50) -> list[dict[str, Any]] | None:
    """Return ETF/portfolio holdings, or ``None`` on fetch failure (see fetch_revenue_trend)."""
    if asset_type not in {"etf", "portfolio"} or limit <= 0:
        return []  # not applicable for this asset type — valid empty
    try:
        from backend.tools.fmp import get_etf_holdings

        rows = get_etf_holdings(symbol, limit=limit)
        if not rows:
            return []
        return [
            {
                "symbol": row["symbol"].strip().upper(),
                "name": row["name"].strip() if isinstance(row.get("name"), str) and row["name"].strip() else row["symbol"].strip().upper(),
                "weight": weight if (weight := safe_float(row.get("weight"))) is not None and 0 <= weight <= 100 else 0.0,
                "shares": safe_float(row.get("shares")) or 0.0,
                "value": safe_float(row.get("value")) or 0.0,
            }
            for row in [r for r in iter_dict_items(rows)
                        if isinstance(r.get("symbol"), str) and r["symbol"].strip()
                        and not r.get("error") and r.get("success") is not False
                        and str(r.get("status") or "").strip().lower() not in {"error", "failed", "unavailable"}][:limit]
        ]
    except Exception as exc:
        logger.warning("[DataService] fetch_holdings failed")
        return None  # exception — do not cache as valid

from backend.dashboard.data_fetchers_equity import (
    _build_ohlcv_frame_from_rows,
    _infer_equity_market,
    _load_ohlcv_frame,
    fetch_analyst_targets,
    fetch_earnings_history,
    fetch_financial_statements,
    fetch_indicator_series,
    fetch_recommendations,
    fetch_technical_indicators,
    fetch_valuation,
)
