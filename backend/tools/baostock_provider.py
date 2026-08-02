from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.utils.quote import safe_float

logger = logging.getLogger(__name__)


def is_cn_symbol(symbol: str) -> bool:
    text = str(symbol or "").strip().upper()
    return text.endswith((".SS", ".SZ", ".BJ"))


def to_baostock_code(symbol: str) -> str | None:
    text = str(symbol or "").strip().upper()
    if text.endswith(".SS"):
        return f"sh.{text[:-3]}"
    if text.endswith(".SZ"):
        return f"sz.{text[:-3]}"
    if text.endswith(".BJ"):
        return f"bj.{text[:-3]}"
    return None


def _load_baostock() -> Any | None:
    try:
        import baostock as bs  # type: ignore

        return bs
    except Exception as exc:
        logger.info('[BaoStock] package unavailable')
        return None


def _history_rows(symbol: str, *, days: int = 90) -> list[dict[str, Any]]:
    bs = _load_baostock()
    code = to_baostock_code(symbol)
    if bs is None or code is None:
        return []

    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=max(days, 10))
    fields = "date,code,open,high,low,close,preclose,volume,amount,pctChg"

    logged_in = False
    try:
        login = bs.login()
        logged_in = getattr(login, "error_code", "0") == "0"
        if not logged_in:
            logger.info("[BaoStock] login failed")
            return []

        result = bs.query_history_k_data_plus(
            code,
            fields,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            frequency="d",
            adjustflag="2",
        )
        rows: list[dict[str, Any]] = []
        while result.error_code == "0" and result.next():
            raw = dict(zip(result.fields, result.get_row_data()))
            close = safe_float(raw.get("close"))
            if close is None:
                continue
            rows.append(
                {
                    "time": raw.get("date"),
                    "open": safe_float(raw.get("open")),
                    "high": safe_float(raw.get("high")),
                    "low": safe_float(raw.get("low")),
                    "close": close,
                    "volume": safe_float(raw.get("volume")),
                    "amount": safe_float(raw.get("amount")),
                    "pctChg": safe_float(raw.get("pctChg")),
                }
            )
        return rows
    except Exception as exc:
        logger.info('[BaoStock] history failed')
        return []
    finally:
        if logged_in:
            try:
                bs.logout()
            except Exception as exc:
                logger.debug('[BaoStock] logout failed')


def fetch_cn_quote(symbol: str) -> dict[str, Any] | None:
    rows = _history_rows(symbol, days=14)
    if not rows:
        return None
    latest = rows[-1]
    previous = rows[-2] if len(rows) >= 2 else None
    price = safe_float(latest.get("close"))
    prev_close = safe_float(previous.get("close")) if previous else None
    if price is None:
        return None

    change = price - prev_close if prev_close not in (None, 0) else None
    change_percent = (change / prev_close * 100) if change is not None and prev_close else latest.get("pctChg")
    as_of = str(latest.get("time") or datetime.now(timezone.utc).date().isoformat())
    return {
        "symbol": symbol.upper(),
        "currentPrice": price,
        "regularMarketPrice": price,
        "price": price,
        "regularMarketChange": change,
        "change": change,
        "regularMarketChangePercent": change_percent,
        "change_percent": change_percent,
        "regularMarketVolume": latest.get("volume"),
        "volume": latest.get("volume"),
        "source": "baostock",
        "as_of": as_of,
        "freshness_status": "live",
        "fallback_level": 1,
        "modelGenerated": False,
    }


def fetch_cn_kline(symbol: str, *, period: str = "1mo", interval: str = "1d") -> dict[str, Any] | None:
    days_by_period = {
        "5d": 10,
        "1mo": 45,
        "3mo": 120,
        "6mo": 220,
        "1y": 420,
        "2y": 760,
    }
    rows = _history_rows(symbol, days=days_by_period.get(period, 120))
    if not rows:
        return None

    dates = [str(row.get("time")) for row in rows]
    values = [
        [row.get("open"), row.get("close"), row.get("low"), row.get("high")]
        for row in rows
    ]
    return {
        "kline_data": rows,
        "dates": dates,
        "values": values,
        "period": period,
        "interval": interval,
        "source": "baostock",
        "as_of": dates[-1] if dates else datetime.now(timezone.utc).isoformat(),
        "freshness_status": "live",
        "fallback_level": 1,
    }


__all__ = ["is_cn_symbol", "to_baostock_code", "fetch_cn_quote", "fetch_cn_kline"]
