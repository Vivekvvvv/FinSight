from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.tools.http import _http_get
from backend.utils.quote import safe_float

_NASDAQ_API_ROOT = "https://api.nasdaq.com/api/quote"
_NASDAQ_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.nasdaq.com/market-activity/stocks/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
}


def _number(value: Any) -> float | None:
    if isinstance(value, str):
        value = value.strip().replace("$", "").replace(",", "").replace("%", "")
        if not value or value.lower() in {"n/a", "na", "--"}:
            return None
    return safe_float(value)


def _get_data(ticker: str, endpoint: str) -> dict[str, Any] | None:
    try:
        response = _http_get(
            f"{_NASDAQ_API_ROOT}/{ticker}/{endpoint}",
            params={"assetclass": "stocks"},
            headers=_NASDAQ_HEADERS,
            timeout=(2, 8),
        )
        if getattr(response, "status_code", 0) != 200:
            return None
        payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) else None
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def fetch_nasdaq_quote(ticker: str) -> dict[str, Any] | None:
    data = _get_data(ticker, "info")
    if data is None:
        return None
    primary = data.get("primaryData") if isinstance(data.get("primaryData"), dict) else {}
    price = _number(primary.get("lastSalePrice"))
    if price is None:
        return None
    return {
        "name": str(data.get("companyName") or ticker).strip() or ticker,
        "price": price,
        "change": _number(primary.get("netChange")),
        "change_percent": _number(primary.get("percentageChange")),
        "volume": _number(primary.get("volume")),
        "market_cap": None,
        "source": "nasdaq_quote",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "freshness_status": "live" if primary.get("isRealTime") else "delayed_15min",
        "fallback_level": 0,
    }


def fetch_nasdaq_intraday(ticker: str) -> dict[str, Any] | None:
    data = _get_data(ticker, "chart")
    if data is None:
        return None
    rows = data.get("chart")
    if not isinstance(rows, list):
        return None
    points: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        timestamp = _number(row.get("x"))
        value = _number(row.get("y"))
        if timestamp is None or value is None:
            continue
        points.append({
            "time": datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).isoformat(),
            "value": value,
        })
    if not points:
        return None
    return {
        "symbol": str(data.get("symbol") or ticker).upper(),
        "line_data": points,
        "chart_kind": "intraday_line",
        "period": "1d",
        "interval": "1m",
        "source": "nasdaq_intraday",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "freshness_status": "live",
        "fallback_level": 0,
    }


__all__ = ["fetch_nasdaq_intraday", "fetch_nasdaq_quote"]
