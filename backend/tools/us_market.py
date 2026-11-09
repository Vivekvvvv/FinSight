from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.tools._item import iter_dict_items
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
    ticker = ticker.strip().upper() if isinstance(ticker, str) else ""
    if not ticker:
        return None
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
        if (isinstance(payload, dict) and (payload.get("error") or payload.get("success") is False
            or str(payload.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}
            or isinstance(payload.get("status"), dict) and payload["status"].get("rCode") not in (None, 200))):
            return None
        if isinstance(payload, dict) and any(
            value is not None and (not isinstance(value, str) or value.strip().upper() != ticker.strip().upper())
            for value in (payload.get("ticker"), payload.get("symbol"))
        ):
            return None
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, dict) and (data.get("error") or data.get("success") is False
            or str(data.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
            return None
        if isinstance(data, dict) and any(
            value is not None and (not isinstance(value, str) or value.strip().upper() != ticker.strip().upper())
            for value in (data.get("ticker"), data.get("symbol"))
        ):
            return None
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def fetch_nasdaq_quote(ticker: str) -> dict[str, Any] | None:
    data = _get_data(ticker, "info")
    if data is None:
        return None
    primary = data.get("primaryData") if isinstance(data.get("primaryData"), dict) else {}
    if (primary.get("error") or primary.get("success") is False
        or str(primary.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
        return None
    if any(value is not None and (not isinstance(value, str) or value.strip().upper() != ticker.strip().upper())
           for value in (primary.get("ticker"), primary.get("symbol"))):
        return None
    price = _number(primary.get("lastSalePrice"))
    if price is None or price <= 0:
        return None
    return {
        "name": name.strip() if isinstance(name := data.get("companyName"), str) and name.strip() else ticker,
        "price": price,
        "change": _number(primary.get("netChange")),
        "change_percent": percentage if (percentage := _number(primary.get("percentageChange"))) is not None and percentage >= -100 else None,
        "volume": volume if (volume := _number(primary.get("volume"))) is not None and volume >= 0 else None,
        "market_cap": None,
        "source": "nasdaq_quote",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "freshness_status": "live" if primary.get("isRealTime") is True else "delayed_15min",
        "fallback_level": 0 if primary.get("isRealTime") is True else 1,
    }


def fetch_nasdaq_intraday(ticker: str) -> dict[str, Any] | None:
    data = _get_data(ticker, "chart")
    if data is None:
        return None
    rows = data.get("chart")
    if not isinstance(rows, list):
        return None
    points: list[dict[str, Any]] = []
    for row in iter_dict_items(rows):
        if (row.get("error") or row.get("success") is False
            or str(row.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
            continue
        if any(value is not None and (not isinstance(value, str) or value.strip().upper() != ticker.strip().upper())
               for value in (row.get("ticker"), row.get("symbol"))):
            continue
        timestamp = _number(row.get("x"))
        value = _number(row.get("y"))
        if timestamp is None or value is None or value <= 0:
            continue
        try:
            ts = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
        except Exception:
            # 单个畸形时间点（超出系统时间范围 → OSError/ValueError）跳过——
            # 一行坏数据不应让整段分时 raise（tools 约定返回 None 不抛）。
            continue
        points.append({
            "time": ts.isoformat(),
            "value": value,
        })
    points = sorted({point["time"]: point for point in points}.values(), key=lambda point: point["time"])
    if not points:
        return None
    return {
        "symbol": str(data.get("symbol") or ticker).strip().upper(),
        "line_data": points,
        "chart_kind": "intraday_line",
        "period": "1d",
        "interval": "1m",
        "source": "nasdaq_intraday",
        # as_of 必须是最后一条分时数据的时间；取数时刻在盘后会让旧图看起来是刚更新的。
        "as_of": points[-1]["time"],
        "freshness_status": "live",
        "fallback_level": 0,
    }


__all__ = ["fetch_nasdaq_intraday", "fetch_nasdaq_quote"]
