# -*- coding: utf-8 -*-
"""Market/snapshot/news data retrieval helpers extracted from data_service.py (round 19)."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

from backend.utils.quote import safe_float

from backend.dashboard.data_providers import (
    _fetch_financial_statements_from_cn_hk_market,
    _fetch_financial_statements_from_finnhub,
    _fetch_financial_statements_from_sec_companyfacts,
    _fetch_valuation_from_cn_hk_market,
    _fetch_valuation_from_finnhub,
)

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


# ══════════════════════════════════════════════════════════════════════════════
# v2 data fetch functions (equity only)
# ══════════════════════════════════════════════════════════════════════════════
# Performance budget (Gate-4):
# ┌──────────────┬─────────┬───────────┬──────────┬───────────────────┐
# │ Source       │ Timeout │ Cache TTL │ Max Par  │ fallback          │
# ├──────────────┼─────────┼───────────┼──────────┼───────────────────┤
# │ valuation    │ 5s      │ 300s(5m)  │ 1        │ return None       │
# │ financials   │ 8s      │ 3600s(1h) │ 1        │ return None       │
# │ technicals   │ 5s      │ 60s       │ 1        │ return None       │
# │ peers        │ 10s     │ 3600s(1h) │ 3(batch) │ return None       │
# └──────────────┴─────────┴───────────┴──────────┴───────────────────┘


def _infer_equity_market(symbol: str) -> str:
    ticker = str(symbol or "").strip().upper()
    if ticker.endswith((".SS", ".SZ", ".BJ")):
        return "CN"
    if ticker.endswith(".HK"):
        return "HK"
    return "US"


def _build_ohlcv_frame_from_rows(rows: list[dict[str, Any]]) -> Optional[pd.DataFrame]:
    records: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        dt = pd.to_datetime(row.get("time"), errors="coerce")
        if pd.isna(dt):
            continue
        records.append(
            {
                "Date": dt,
                "Open": safe_float(row.get("open")),
                "High": safe_float(row.get("high")),
                "Low": safe_float(row.get("low")),
                "Close": safe_float(row.get("close")),
                "Volume": safe_float(row.get("volume")) or 0.0,
            }
        )
    if not records:
        return None
    frame = pd.DataFrame.from_records(records)
    frame = frame.dropna(subset=["Date", "Open", "High", "Low", "Close"])
    if frame.empty:
        return None
    return frame.sort_values("Date").set_index("Date")


def _load_ohlcv_frame(symbol: str, period: str = "1y", interval: str = "1d") -> Optional[pd.DataFrame]:
    """Load OHLCV frame with yfinance primary + shared multi-source fallback."""
    market = _infer_equity_market(symbol)
    if market in {"CN", "HK"}:
        # 忽略 period/interval 会把固定 300 根日线冒充任何请求（5y 被静默截断、
        # 周线/小时视图拿到日线）。映射传下去；不支持的 interval 跳过东财走 yfinance。
        try:
            from backend.tools.cn_hk_market import fetch_cn_hk_kline, kline_params_for

            kline_params = kline_params_for(period, interval)
            if kline_params is not None:
                klt, limit = kline_params
                cn_hk_rows = fetch_cn_hk_kline(symbol, limit=limit, klt=klt)
                frame = _build_ohlcv_frame_from_rows(cn_hk_rows)
                if frame is not None and not frame.empty:
                    return frame
        except Exception as exc:
            logger.warning("[DataService] CN/HK OHLCV fallback failed")

    try:
        import yfinance as yf

        hist = yf.Ticker(symbol).history(period=period, interval=interval)
        if hist is not None and not hist.empty:
            return hist
    except Exception as exc:
        logger.warning("[DataService] yfinance OHLCV failed")

    # Fast fallback: Stooq is usually quicker than the full multi-source pipeline
    # and helps avoid technical tab timeouts when yfinance is rate-limited.
    try:
        from backend.tools.price import _fetch_with_stooq_history

        payload = _fetch_with_stooq_history(symbol, period=period, interval=interval)
        if isinstance(payload, dict):
            rows = payload.get("kline_data") or []
            frame = _build_ohlcv_frame_from_rows(rows)
            if frame is not None and not frame.empty:
                logger.info("[DataService] OHLCV fallback hit via Stooq")
                return frame
    except Exception as exc:
        logger.warning("[DataService] Stooq OHLCV fallback failed")

    try:
        from backend.tools.price import get_stock_historical_data

        payload = get_stock_historical_data(symbol, period=period, interval=interval)
        if not isinstance(payload, dict):
            return None
        rows = payload.get("kline_data") or []
        if not isinstance(rows, list) or not rows:
            return None

        frame = _build_ohlcv_frame_from_rows(rows)
        if frame is None or frame.empty:
            return None
        logger.info("[DataService] OHLCV fallback hit via price pipeline")
        return frame
    except Exception as exc:
        logger.warning("[DataService] fallback OHLCV failed")
        return None


def fetch_valuation(symbol: str) -> dict[str, Any] | None:
    """Fetch valuation metrics from yfinance Ticker.info.

    Returns a dict matching the ValuationData schema fields, or None on
    failure.
    """
    market = _infer_equity_market(symbol)
    if market in {"CN", "HK"}:
        cn_hk_fallback = _fetch_valuation_from_cn_hk_market(symbol)
        if cn_hk_fallback:
            logger.info("[DataService] valuation fallback via CN/HK source")
            return cn_hk_fallback

    try:
        import yfinance as yf

        info = yf.Ticker(symbol).info or {}
        result = {
            "market_cap": safe_float(info.get("marketCap")),
            "trailing_pe": safe_float(info.get("trailingPE")),
            "forward_pe": safe_float(info.get("forwardPE")),
            "price_to_book": safe_float(info.get("priceToBook")),
            "price_to_sales": safe_float(info.get("priceToSalesTrailing12Months")),
            "ev_to_ebitda": safe_float(info.get("enterpriseToEbitda")),
            "dividend_yield": safe_float(info.get("dividendYield")),
            "beta": safe_float(info.get("beta")),
            "week52_high": safe_float(info.get("fiftyTwoWeekHigh")),
            "week52_low": safe_float(info.get("fiftyTwoWeekLow")),
        }
        if any(v is not None for v in result.values()):
            return result
    except Exception as exc:
        logger.warning("[DataService] fetch_valuation failed")

    fallback = _fetch_valuation_from_finnhub(symbol)
    if fallback:
        logger.info("[DataService] valuation fallback via Finnhub")
        return fallback

    if market in {"CN", "HK"}:
        cn_hk_fallback = _fetch_valuation_from_cn_hk_market(symbol)
        if cn_hk_fallback:
            logger.info("[DataService] valuation late fallback via CN/HK source")
            return cn_hk_fallback
    return None


def fetch_financial_statements(symbol: str, periods: int = 8) -> dict[str, Any] | None:
    """Fetch quarterly financial statements from yfinance.

    Returns a dict matching the FinancialStatement schema, or None on
    failure.
    """
    market = _infer_equity_market(symbol)
    if market in {"CN", "HK"}:
        cn_hk_payload = _fetch_financial_statements_from_cn_hk_market(symbol, periods=periods)
        if cn_hk_payload:
            logger.info("[DataService] financials fallback via CN/HK source")
            return cn_hk_payload

    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)

        def _period_label(col: Any) -> str:
            if isinstance(col, pd.Timestamp):
                return f"{col.year}Q{(col.month - 1) // 3 + 1}"
            text = str(col).strip()
            if len(text) >= 10 and text[4] == "-" and text[7] == "-":
                try:
                    dt = pd.to_datetime(text)
                    return f"{dt.year}Q{(dt.month - 1) // 3 + 1}"
                except Exception:
                    return text[:10]
            return text[:10]

        def _valid_frame(frame: Optional[pd.DataFrame]) -> bool:
            return frame is not None and hasattr(frame, "empty") and not frame.empty

        def _build_label_map(frame: Optional[pd.DataFrame]) -> dict[str, Any]:
            if not _valid_frame(frame):
                return {}
            mapping: dict[str, Any] = {}
            for col in frame.columns:
                label = _period_label(col)
                if label and label not in mapping:
                    mapping[label] = col
            return mapping

        def _locate_row(frame: Optional[pd.DataFrame], candidates: list[str]) -> Optional[pd.Series]:
            if not _valid_frame(frame):
                return None
            index_lookup = {str(idx).strip().lower(): idx for idx in frame.index}
            for candidate in candidates:
                key = candidate.strip().lower()
                if key in index_lookup:
                    return frame.loc[index_lookup[key]]
            return None

        def _extract_series(frame: Optional[pd.DataFrame], candidates: list[str], labels: list[str]) -> list[Optional[float]]:
            if not labels:
                return []
            row = _locate_row(frame, candidates)
            if row is None:
                return [None for _ in labels]
            label_map = _build_label_map(frame)
            output: list[Optional[float]] = []
            for label in labels:
                col = label_map.get(label)
                output.append(safe_float(row.get(col)) if col is not None else None)
            return output

        income = getattr(ticker, "quarterly_income_stmt", None)
        if income is None or (hasattr(income, "empty") and income.empty):
            income = getattr(ticker, "quarterly_financials", None)
        balance = getattr(ticker, "quarterly_balance_sheet", None)
        cashflow = getattr(ticker, "quarterly_cashflow", None)

        label_candidates: list[str] = []
        for frame in (income, balance, cashflow):
            for label in _build_label_map(frame).keys():
                if label not in label_candidates:
                    label_candidates.append(label)

        period_labels = label_candidates[:periods]
        if not period_labels:
            sec_fallback = _fetch_financial_statements_from_sec_companyfacts(symbol, periods=periods)
            if sec_fallback:
                logger.info("[DataService] financials empty-period fallback via SEC companyfacts")
                return sec_fallback
            fallback = _fetch_financial_statements_from_finnhub(symbol, periods=periods)
            if fallback:
                logger.info("[DataService] financials empty-period fallback via Finnhub")
                return fallback
            return None

        result: dict[str, Any] = {
            "periods": period_labels,
            "revenue": _extract_series(income, ["Total Revenue", "Revenue", "Net Sales", "Operating Revenue"], period_labels),
            "gross_profit": _extract_series(income, ["Gross Profit"], period_labels),
            "operating_income": _extract_series(income, ["Operating Income", "Operating Income Loss"], period_labels),
            "net_income": _extract_series(income, ["Net Income", "Net Income Common Stockholders"], period_labels),
            "eps": _extract_series(income, ["Basic EPS", "Diluted EPS"], period_labels),
            "total_assets": _extract_series(balance, ["Total Assets", "Total Asset"], period_labels),
            "total_liabilities": _extract_series(
                balance,
                ["Total Liabilities Net Minority Interest", "Total Liabilities", "Total Liab", "Liabilities"],
                period_labels,
            ),
            "operating_cash_flow": _extract_series(
                cashflow,
                ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities", "Operating Cash Flow"],
                period_labels,
            ),
            "free_cash_flow": _extract_series(cashflow, ["Free Cash Flow"], period_labels),
        }
        metric_fields = [
            "revenue",
            "gross_profit",
            "operating_income",
            "net_income",
            "eps",
            "total_assets",
            "total_liabilities",
            "operating_cash_flow",
            "free_cash_flow",
        ]
        has_any_value = any(
            any(value is not None for value in (result.get(field) or []))
            for field in metric_fields
        )
        if has_any_value:
            return result

        sec_fallback = _fetch_financial_statements_from_sec_companyfacts(symbol, periods=periods)
        if sec_fallback:
            logger.info("[DataService] financials empty-result fallback via SEC companyfacts")
            return sec_fallback

        fallback = _fetch_financial_statements_from_finnhub(symbol, periods=periods)
        if fallback:
            logger.info("[DataService] financials empty-result fallback via Finnhub")
            return fallback
        return None
    except Exception as exc:
        logger.warning("[DataService] fetch_financial_statements failed")
        sec_fallback = _fetch_financial_statements_from_sec_companyfacts(symbol, periods=periods)
        if sec_fallback:
            logger.info("[DataService] financials exception fallback via SEC companyfacts")
            return sec_fallback
        fallback = _fetch_financial_statements_from_finnhub(symbol, periods=periods)
        if fallback:
            logger.info("[DataService] financials exception fallback via Finnhub")
            return fallback
        return None


def fetch_technical_indicators(symbol: str) -> dict[str, Any] | None:
    """Compute technical indicators for *symbol*.

    Fetches 1-year daily OHLCV via yfinance and delegates to
    :func:`backend.tools.technical.compute_technical_indicators`.
    """
    try:
        from backend.tools.technical import compute_technical_indicators

        hist = _load_ohlcv_frame(symbol, period="1y", interval="1d")
        if hist is None or hist.empty:
            return None

        result = compute_technical_indicators(hist)
        return result if result else None
    except Exception as exc:
        logger.warning("[DataService] fetch_technical_indicators failed")
        return None


def fetch_indicator_series(symbol: str, n_days: int = 120) -> dict[str, Any] | None:
    """Compute RSI/MACD/BB time series for *symbol* (Phase G2)."""
    try:
        from backend.tools.technical import compute_indicator_series

        hist = _load_ohlcv_frame(symbol, period="1y", interval="1d")
        if hist is None or hist.empty:
            return None

        result = compute_indicator_series(hist, n_days)
        return result if result else None
    except Exception as exc:
        logger.warning("[DataService] fetch_indicator_series failed")
        return None


def fetch_earnings_history(symbol: str) -> list[dict[str, Any]] | None:
    """Fetch EPS estimate vs actual history from yfinance (Phase G2)."""
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        eh = getattr(ticker, "earnings_history", None)
        if eh is None or (hasattr(eh, "empty") and eh.empty):
            return None

        # yfinance returns a DataFrame with columns like
        # 'epsEstimate', 'epsActual', 'epsDifference', 'surprisePercent'
        import pandas as pd
        if isinstance(eh, pd.DataFrame):
            entries: list[dict[str, Any]] = []
            for idx, row in eh.iterrows():
                quarter_str = str(idx) if idx is not None else ""
                if hasattr(idx, "strftime"):
                    quarter_str = idx.strftime("%Y-%m-%d")
                entries.append({
                    "quarter": quarter_str,
                    "eps_estimate": safe_float(row.get("epsEstimate")),
                    "eps_actual": safe_float(row.get("epsActual")),
                    "surprise_pct": safe_float(row.get("surprisePercent")),
                })
            return entries if entries else None
        return None
    except Exception as exc:
        logger.warning("[DataService] fetch_earnings_history failed")
        return None


def fetch_analyst_targets(symbol: str) -> dict[str, Any] | None:
    """Fetch analyst price targets from yfinance (Phase G2)."""
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        targets = getattr(ticker, "analyst_price_targets", None)
        if targets is None:
            return None

        import pandas as pd
        if isinstance(targets, pd.DataFrame):
            # Some yfinance versions return a DataFrame, others a dict
            if targets.empty:
                return None
            row = targets.iloc[0] if len(targets) > 0 else {}
            result = {
                "low": safe_float(row.get("low")),
                "current": safe_float(row.get("current")),
                "mean": safe_float(row.get("mean")),
                "median": safe_float(row.get("median")),
                "high": safe_float(row.get("high")),
            }
        elif isinstance(targets, dict):
            result = {
                "low": safe_float(targets.get("low")),
                "current": safe_float(targets.get("current")),
                "mean": safe_float(targets.get("mean")),
                "median": safe_float(targets.get("median")),
                "high": safe_float(targets.get("high")),
            }
        else:
            return None

        if all(v is None for v in result.values()):
            return None
        return result
    except Exception as exc:
        logger.warning("[DataService] fetch_analyst_targets failed")
        return None


def fetch_recommendations(symbol: str) -> dict[str, Any] | None:
    """Fetch analyst recommendation summary from yfinance (Phase G2)."""
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        rec = getattr(ticker, "recommendations_summary", None)
        if rec is None:
            return None

        import pandas as pd
        if isinstance(rec, pd.DataFrame) and not rec.empty:
            # int(row.get(bucket, 0)) 的默认 0 只挡 key 缺失；若单元格存在但为
            # NaN（yfinance 部分数据），int(nan) 抛 ValueError 被外层 except 吞成
            # 整块 None → 一个桶 NaN 就丢掉整个分析师评级组件。safe_float 把
            # NaN/None 归一为 None，该桶降级为 0 不牵连其余（R60）。
            row = rec.iloc[0]
            result = {
                "strong_buy": int(safe_float(row.get("strongBuy", 0)) or 0),
                "buy": int(safe_float(row.get("buy", 0)) or 0),
                "hold": int(safe_float(row.get("hold", 0)) or 0),
                "sell": int(safe_float(row.get("sell", 0)) or 0),
                "strong_sell": int(safe_float(row.get("strongSell", 0)) or 0),
            }
            if sum(result.values()) == 0:
                return None
            return result
        return None
    except Exception as exc:
        logger.warning("[DataService] fetch_recommendations failed")
        return None
