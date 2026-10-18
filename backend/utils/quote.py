"""Shared quote parsing & float conversion utilities.

Single source of truth — all routers/services MUST import from here.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _freshness_status(source: str) -> str:
    """Map source tag to a human-readable freshness label."""
    if source == "tools_bridge":
        return "live"
    if source == "yfinance_fallback":
        # 兜底走的是 5 日线日线收盘，不是 15 分钟延迟报价；
        # 标成 delayed_15min 会让用户以为这是盘中价。
        return "stale"
    if source == "cache":
        return "cached"
    return "unknown"


def _fallback_level(source: str) -> int:
    """0 = primary live feed, 1 = yfinance fallback, 2 = cache."""
    if source == "tools_bridge":
        return 0
    if source == "yfinance_fallback":
        return 1
    return 2


def safe_float(value: Any) -> Optional[float]:
    """Convert *value* to float; return None for invalid numbers."""
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return None
        return out
    except (TypeError, ValueError, OverflowError):
        return None


def safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    """Convert *value* to int; return *default* for invalid numbers."""
    if value is None or isinstance(value, bool):
        return default
    if isinstance(value, float) and not math.isfinite(value):
        return default
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def parse_quote_payload(payload: Any) -> dict[str, Any] | None:
    """Parse raw quote payload into ``{price, change, change_percent}``."""
    if payload is None:
        return None

    if isinstance(payload, dict):
        nested = payload.get("data")
        if nested is not None:
            inner = parse_quote_payload(nested)
            if inner:
                return inner

        price = safe_float(payload.get("price"))
        if price is not None:
            return {
                "price": price,
                "change": safe_float(payload.get("change")),
                "change_percent": safe_float(payload.get("change_percent")),
            }
        return None

    text = str(payload)
    price_match = re.search(r"Current Price:\s*\$([0-9.,]+)", text, re.IGNORECASE)
    # 兜底/涨跌额正则须允许千分位逗号并在使用时剥除，否则 "$1,234.56" 在逗号处
    # 截断成 "1" → price=1.0（约 1000× 低估）；change "-1,234.5" → "-1"（R41）。
    fallback_price_match = re.search(r"\$([0-9][0-9,]*(?:\.[0-9]+)?)", text)
    change_match = re.search(r"Change:\s*([+-]?[0-9][0-9,]*(?:\.[0-9]+)?)", text, re.IGNORECASE)
    pct_match = re.search(r"\(([-+]?[0-9.]+)%\)", text)

    price_text = (
        price_match.group(1).replace(",", "")
        if price_match
        else (fallback_price_match.group(1).replace(",", "") if fallback_price_match else None)
    )
    price = safe_float(price_text) if price_text else None
    if price is None:
        return None

    return {
        "price": price,
        "change": safe_float(change_match.group(1).replace(",", "")) if change_match else None,
        "change_percent": safe_float(pct_match.group(1)) if pct_match else None,
    }


def fallback_quote_yfinance(ticker: str) -> dict[str, Any] | None:
    """Last-resort quote fetch via yfinance 5-day daily history."""
    try:
        import yfinance as yf

        hist = yf.Ticker(ticker).history(period="5d", interval="1d")
        if hist is None or hist.empty:
            return None

        close = safe_float(hist["Close"].iloc[-1])
        if close is None:
            return None

        prev_close = safe_float(hist["Close"].iloc[-2]) if len(hist) > 1 else None
        change = (close - prev_close) if prev_close not in (None, 0.0) else None
        change_pct = ((change / prev_close) * 100.0) if change is not None and prev_close else None
        result = {
            "price": close,
            "change": change,
            "change_percent": change_pct,
            "source": "yfinance_fallback",
            # 日线收盘的时间戳才是这批数据的真实 as_of；不能用取数时刻冒充。
            "freshness_status": "stale",
        }
        last_bar = hist.index[-1]
        if hasattr(last_bar, "isoformat"):
            result["as_of"] = last_bar.isoformat()
        return result
    except Exception:
        return None


_KNOWN_FRESHNESS = {"live", "delayed_15min", "cached", "stale", "demo", "fallback", "unknown"}
_FRESHNESS_FALLBACK_LEVEL = {
    "live": 0,
    "delayed_15min": 1,
    "fallback": 1,
    "cached": 2,
    "stale": 2,
    "demo": 2,
}


def _payload_meta(payload: Any) -> dict[str, Any]:
    """取上游报价自带的元数据，兼容 ``{data: {...}}`` 包裹（内层优先）。"""
    if not isinstance(payload, dict):
        return {}
    nested = payload.get("data")
    if isinstance(nested, dict):
        return {**payload, **nested}
    return payload


def _meta_freshness(meta: dict[str, Any]) -> str | None:
    """未提供返回 None（沿用旧默认）；提供了但非法则明确标 unknown。"""
    if "freshness_status" not in meta:
        return None
    value = str(meta.get("freshness_status") or "").strip().lower()
    return value if value in _KNOWN_FRESHNESS else "unknown"


def declared_quote_freshness(payload: Any) -> str | None:
    """上游载荷声明的 freshness_status（兼容 ``{data: {...}}`` 包裹）。

    ``parse_quote_payload`` 只保留价格字段；需要区分实时/缓存/延迟的调用方
    必须另行取这个标签，否则会把缓存价统一当成实时。未声明返回 None。
    """
    return _meta_freshness(_payload_meta(payload))


def _meta_as_of(meta: dict[str, Any]) -> str | None:
    value = meta.get("as_of")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _meta_fallback_level(meta: dict[str, Any]) -> int | None:
    value = meta.get("fallback_level")
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value in (0, 1, 2):
        return value
    return None


def resolve_live_quote(
    ticker: str,
    get_stock_price: Any = None,
) -> tuple[dict[str, Any] | None, Any]:
    """Resolve quote via tools bridge first, then yfinance fallback.

    Returns ``(parsed_quote, raw_payload)``.

    上游工具可能返回缓存/延迟数据。``parse_quote_payload`` 只保留价格字段，
    所以这里必须把上游的 ``freshness_status``/``as_of``/``fallback_level``
    带回结果；否则缓存报价会被统一盖成 live + 当前时间，对外伪造实时。
    """
    raw_payload: Any = None

    if get_stock_price is not None:
        try:
            raw_payload = get_stock_price(ticker)
        except Exception:
            raw_payload = None

        parsed = parse_quote_payload(raw_payload)
        if parsed:
            meta = _payload_meta(raw_payload)
            freshness = _meta_freshness(meta) or "live"
            upstream_level = _meta_fallback_level(meta)
            parsed["source"] = "tools_bridge"
            parsed["as_of"] = _meta_as_of(meta) or _now_iso()
            parsed["freshness_status"] = freshness
            parsed["fallback_level"] = (
                upstream_level if upstream_level is not None
                else _FRESHNESS_FALLBACK_LEVEL.get(freshness, 0)
            )
            return parsed, raw_payload

    fallback = fallback_quote_yfinance(ticker)
    if fallback:
        fallback.setdefault("as_of", _now_iso())
        fallback.setdefault("freshness_status", _freshness_status(fallback.get("source", "yfinance_fallback")))
        fallback.setdefault("fallback_level", _fallback_level(fallback.get("source", "yfinance_fallback")))
        return fallback, raw_payload

    return None, raw_payload
