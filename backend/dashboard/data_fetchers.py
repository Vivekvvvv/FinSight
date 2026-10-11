# -*- coding: utf-8 -*-
"""Market/snapshot/news data retrieval helpers extracted from data_service.py (round 19)."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

from backend.utils.quote import safe_float

from backend.dashboard.news_ranking import (
    _empty_news_payload,
    _news_ranking_meta,
    _parse_news_text,
    _rank_news_items,
    _to_news_item,
    _ts_seconds,
)

logger = logging.getLogger(__name__)


_FEAR_GREED_PATTERN = re.compile(
    r"(?:fear\s*&?\s*greed(?:\s*index)?|恐惧贪婪指数)[^0-9]{0,20}([0-9]{1,3}(?:\.\d+)?)",
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
    return max(0.0, min(100.0, value))


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
        if isinstance(fred_payload, dict):
            for key in ("fed_rate", "cpi", "unemployment", "gdp_growth", "treasury_10y", "yield_spread"):
                value = safe_float(fred_payload.get(key))
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
            ts = _parse_time_to_unix(ts_index)
            if ts is None:
                continue
            output.append(
                {
                    "time": ts,
                    "open": safe_float(row.get("Open")),
                    "high": safe_float(row.get("High")),
                    "low": safe_float(row.get("Low")),
                    "close": safe_float(row.get("Close")),
                    "volume": safe_float(row.get("Volume")) or 0,
                }
            )
        return output
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
            info = {}

        last_close = None
        try:
            hist = ticker.history(period="5d", interval="1d")
            if hist is not None and not hist.empty:
                last_close = safe_float(hist["Close"].iloc[-1])
        except Exception:
            last_close = None

        output: dict[str, Any] = {}
        if asset_type == "equity":
            output.update(
                {
                    "revenue": safe_float(info.get("totalRevenue")),
                    # trailingEps=0.0（盈亏平衡）是真实值，裸 `or` 会把它当缺失、
                    # 用 forwardEps（预测值）顶替——显式 None 判断，只在缺失时回退。
                    "eps": safe_float(
                        info.get("trailingEps")
                        if info.get("trailingEps") is not None
                        else info.get("forwardEps")
                    ),
                    "gross_margin": safe_float(info.get("grossMargins")),
                    "fcf": safe_float(info.get("freeCashflow")),
                }
            )
        elif asset_type in {"index", "crypto"}:
            if last_close is not None:
                output["index_level"] = last_close
        elif asset_type == "etf":
            nav = safe_float(info.get("navPrice"))
            output["nav"] = nav if nav is not None else last_close

        return output
    except Exception as exc:
        logger.warning("[DataService] fetch_snapshot failed")
        return None  # failure — do not cache


def fetch_revenue_trend(symbol: str) -> list[dict[str, Any]]:
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

        output.reverse()
        return output[-8:]
    except Exception as exc:
        logger.warning("[DataService] fetch_revenue_trend failed")
        return []


def fetch_segment_mix(symbol: str) -> list[dict[str, Any]]:
    try:
        from backend.tools.fmp import get_revenue_product_segmentation

        rows = get_revenue_product_segmentation(symbol)
        if not rows:
            return []
        return [
            {
                "name": row.get("segment", "Unknown"),
                "value": row.get("revenue", 0),
                "weight": row.get("percentage", 0) / 100,
            }
            for row in rows
        ]
    except Exception as exc:
        logger.warning("[DataService] fetch_segment_mix failed")
        return []


def fetch_news(symbol: str, limit: int = 20) -> dict[str, Any] | None:
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
                impact_ok = True
                if isinstance(raw_impact, list):
                    impact_items = raw_impact
                elif isinstance(raw_impact, str):
                    impact_items = _parse_news_text(raw_impact)
            except (FuturesTimeout, Exception) as exc:
                logger.warning("[DataService] get_company_news failed")

            try:
                raw_market = f_market.result(timeout=30)
                market_ok = True
                if isinstance(raw_market, list):
                    market_items = raw_market
                elif isinstance(raw_market, str):
                    market_items = _parse_news_text(raw_market)
            except (FuturesTimeout, Exception) as exc:
                logger.warning("[DataService] get_market_news_headlines failed")
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

        # 两个来源都抛异常（而非都返回空列表）→ 视为 news 管道故障，返回 None。
        # 此前无论如何都返回空 payload，而 router 只把 None 当失败，导致真实
        # 故障被当成"高置信度无新闻"、缓存 TTL_NEWS 时长且不标 fallback（R51）。
        if not impact_ok and not market_ok:
            return None

        market_raw = [_to_news_item(item) for item in market_items[:limit]]
        impact_raw = [_to_news_item(item) for item in impact_items[:limit]]

        result = {
            "market": _rank_news_items(market_raw, limit, symbol=symbol, mode="market"),
            "impact": _rank_news_items(impact_raw, limit, symbol=symbol, mode="impact"),
            "market_raw": market_raw,
            "impact_raw": impact_raw,
            "ranking_meta": _news_ranking_meta(),
        }
        return result
    except Exception as exc:
        logger.warning("[DataService] fetch_news failed")
        return _empty_news_payload()


def fetch_sector_weights(symbol: str, asset_type: str) -> list[dict[str, Any]]:
    if asset_type not in {"etf", "index"}:
        return []
    try:
        from backend.tools.fmp import get_etf_sector_weights

        rows = get_etf_sector_weights(symbol)
        if not rows:
            return []
        return [
            {"name": row.get("sector", "Unknown"), "weight": row.get("weight", 0) / 100}
            for row in rows
        ]
    except Exception as exc:
        logger.warning("[DataService] fetch_sector_weights failed")
        return []


def fetch_top_constituents(symbol: str, asset_type: str, limit: int = 10) -> list[dict[str, Any]]:
    if asset_type != "index":
        return []
    try:
        from backend.tools.fmp import get_index_constituents

        rows = get_index_constituents(symbol)
        if not rows:
            return []
        return [
            {
                "symbol": row.get("symbol", ""),
                "name": row.get("name", ""),
                "weight": row.get("weight", 0),
            }
            for row in rows[:limit]
        ]
    except Exception as exc:
        logger.warning("[DataService] fetch_top_constituents failed")
        return []


def fetch_holdings(symbol: str, asset_type: str, limit: int = 50) -> list[dict[str, Any]]:
    if asset_type not in {"etf", "portfolio"}:
        return []
    try:
        from backend.tools.fmp import get_etf_holdings

        rows = get_etf_holdings(symbol, limit=limit)
        if not rows:
            return []
        return [
            {
                "symbol": row.get("symbol", ""),
                "name": row.get("name", ""),
                "weight": row.get("weight", 0),
                "shares": row.get("shares", 0),
                "value": row.get("value", 0),
            }
            for row in rows[:limit]
        ]
    except Exception as exc:
        logger.warning("[DataService] fetch_holdings failed")
        return []

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
