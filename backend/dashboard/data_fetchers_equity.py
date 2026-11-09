# -*- coding: utf-8 -*-
"""Equity-focused v2 data fetchers extracted from data_fetchers.py."""

from __future__ import annotations

import logging
from typing import Any, Optional

import pandas as pd

from backend.tools._item import iter_dict_items
from backend.utils.quote import safe_float

from backend.dashboard.data_providers import (
    _fetch_financial_statements_from_cn_hk_market,
    _fetch_financial_statements_from_finnhub,
    _fetch_financial_statements_from_sec_companyfacts,
    _fetch_valuation_from_cn_hk_market,
    _fetch_valuation_from_finnhub,
)

logger = logging.getLogger(__name__)




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
    if ticker.endswith((".SS", ".SH", ".SZ", ".BJ")) or ticker.isdigit() and len(ticker) == 6:
        return "CN"
    if ticker.endswith(".HK"):
        return "HK"
    return "US"


def _build_ohlcv_frame_from_rows(rows: list[dict[str, Any]], symbol: str | None = None) -> Optional[pd.DataFrame]:
    records: list[dict[str, Any]] = []
    for row in iter_dict_items(rows):
        error = row.get("error")
        if (error and not (isinstance(error, float) and pd.isna(error)) or row.get("success") is False
            or str(row.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
            continue
        if symbol and any(value is not None and not (isinstance(value, float) and pd.isna(value))
                          and str(value).strip().upper() != symbol.strip().upper()
                          for value in (row.get("ticker"), row.get("symbol"))):
            continue
        if not isinstance(row.get("time"), (str, pd.Timestamp)):
            continue
        dt = pd.to_datetime(row.get("time"), errors="coerce", utc=True)
        if pd.isna(dt):
            continue
        dt = dt.tz_convert(None)
        records.append(
            {
                "Date": dt,
                "Open": safe_float(row.get("open")),
                "High": safe_float(row.get("high")),
                "Low": safe_float(row.get("low")),
                "Close": safe_float(row.get("close")),
                "Volume": max(0.0, safe_float(row.get("volume")) or 0.0),
            }
        )
    if not records:
        return None
    frame = pd.DataFrame.from_records(records)
    frame = frame.dropna(subset=["Date", "Open", "High", "Low", "Close"])
    frame = frame[(frame[["Open", "High", "Low", "Close"]] > 0).all(axis=1)
                  & (frame["Low"] <= frame[["Open", "Close"]].min(axis=1))
                  & (frame["High"] >= frame[["Open", "Close"]].max(axis=1))]
    if frame.empty:
        return None
    return frame.drop_duplicates(subset=["Date"], keep="last").sort_values("Date").set_index("Date")


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
                frame = _build_ohlcv_frame_from_rows(cn_hk_rows, symbol)
                if frame is not None and not frame.empty:
                    return frame
        except Exception as exc:
            logger.warning("[DataService] CN/HK OHLCV fallback failed")

    try:
        import yfinance as yf

        hist = yf.Ticker(symbol).history(period=period, interval=interval)
        if isinstance(hist, pd.DataFrame) and not hist.empty:
            rows = [{**row.to_dict(), "time": index, **{field.lower(): row.get(field)
                     for field in ("Open", "High", "Low", "Close", "Volume")}} for index, row in hist.iterrows()]
            frame = _build_ohlcv_frame_from_rows(rows, symbol)
            if frame is not None and not frame.empty:
                return frame
    except Exception as exc:
        logger.warning("[DataService] yfinance OHLCV failed")

    # Fast fallback: Stooq is usually quicker than the full multi-source pipeline
    # and helps avoid technical tab timeouts when yfinance is rate-limited.
    try:
        from backend.tools.price import _fetch_with_stooq_history

        payload = _fetch_with_stooq_history(symbol, period=period, interval=interval)
        if (isinstance(payload, dict) and not payload.get("error") and payload.get("success") is not False
            and str(payload.get("status") or "").strip().lower() not in {"error", "failed", "unavailable"}
            and all(value is None or str(value).strip().upper() == symbol.strip().upper()
                    for value in (payload.get("ticker"), payload.get("symbol")))):
            rows = payload.get("kline_data") or []
            frame = _build_ohlcv_frame_from_rows(rows, symbol)
            if frame is not None and not frame.empty:
                logger.info("[DataService] OHLCV fallback hit via Stooq")
                return frame
    except Exception as exc:
        logger.warning("[DataService] Stooq OHLCV fallback failed")

    try:
        from backend.tools.price import get_stock_historical_data

        payload = get_stock_historical_data(symbol, period=period, interval=interval)
        if (not isinstance(payload, dict) or payload.get("error") or payload.get("success") is False
            or str(payload.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
            return None
        if any(value is not None and str(value).strip().upper() != symbol.strip().upper()
               for value in (payload.get("ticker"), payload.get("symbol"))):
            return None
        rows = payload.get("kline_data") or []
        if not isinstance(rows, list) or not rows:
            return None

        frame = _build_ohlcv_frame_from_rows(rows, symbol)
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
        if (info.get("error") or info.get("success") is False
            or str(info.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
            info = {}
        if any(value is not None and str(value).strip().upper() != symbol.strip().upper()
               for value in (info.get("ticker"), info.get("symbol"))):
            info = {}
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
        if result["dividend_yield"] is not None and result["dividend_yield"] < 0:
            result["dividend_yield"] = None
        for key in ("market_cap", "week52_high", "week52_low"):
            if result[key] is not None and result[key] <= 0:
                result[key] = None
        if (result["week52_high"] is not None and result["week52_low"] is not None
            and result["week52_high"] < result["week52_low"]):
            result["week52_high"] = result["week52_low"] = None
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
    if periods <= 0:
        return None
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

        period_labels = sorted(label_candidates, reverse=True)[:periods]
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
    if n_days <= 0:
        return None
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
                if ((isinstance(row.get("error"), str) and row["error"].strip()) or row.get("success") is False
                    or str(row.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
                    continue
                if any(value is not None and not (isinstance(value, float) and pd.isna(value))
                       and (not isinstance(value, str) or value.strip().upper() != symbol.strip().upper())
                       for value in (row.get("ticker"), row.get("symbol"))):
                    continue
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
            if ((isinstance(row.get("error"), str) and row["error"].strip()) or row.get("success") is False
                or str(row.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
                return None
            if any(value is not None and (not isinstance(value, str) or value.strip().upper() != symbol.strip().upper())
                   for value in (row.get("ticker"), row.get("symbol"))):
                return None
            result = {
                "low": safe_float(row.get("low")),
                "current": safe_float(row.get("current")),
                "mean": safe_float(row.get("mean")),
                "median": safe_float(row.get("median")),
                "high": safe_float(row.get("high")),
            }
        elif isinstance(targets, dict):
            if (targets.get("error") or targets.get("success") is False
                or str(targets.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
                return None
            if any(value is not None and (not isinstance(value, str) or value.strip().upper() != symbol.strip().upper())
                   for value in (targets.get("ticker"), targets.get("symbol"))):
                return None
            result = {
                "low": safe_float(targets.get("low")),
                "current": safe_float(targets.get("current")),
                "mean": safe_float(targets.get("mean")),
                "median": safe_float(targets.get("median")),
                "high": safe_float(targets.get("high")),
            }
        else:
            return None

        result = {key: value if value is not None and value > 0 else None for key, value in result.items()}
        low, high = result["low"], result["high"]
        if ((low is not None and high is not None and low > high)
            or any(value is not None and ((low is not None and value < low) or (high is not None and value > high))
                   for value in (result["mean"], result["median"]))):
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
            if ((isinstance(row.get("error"), str) and row["error"].strip()) or row.get("success") is False
                or str(row.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
                return None
            if any(value is not None and (not isinstance(value, str) or value.strip().upper() != symbol.strip().upper())
                   for value in (row.get("ticker"), row.get("symbol"))):
                return None
            def _count(value: Any) -> int:
                number = safe_float(value)
                return int(number) if number is not None and number >= 0 and number.is_integer() else 0

            result = {
                "strong_buy": _count(row.get("strongBuy", 0)),
                "buy": _count(row.get("buy", 0)),
                "hold": _count(row.get("hold", 0)),
                "sell": _count(row.get("sell", 0)),
                "strong_sell": _count(row.get("strongSell", 0)),
            }
            if sum(result.values()) == 0:
                return None
            return result
        return None
    except Exception as exc:
        logger.warning("[DataService] fetch_recommendations failed")
        return None
