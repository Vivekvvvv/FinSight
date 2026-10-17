from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


DEMO_SOURCES = {"demo", "static_market_demo"}
CACHED_SOURCES = {"cache", "cached"}
FALLBACK_SOURCES = {"baostock", "yfinance", "eastmoney"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_KNOWN_FRESHNESS = {"live", "delayed_15min", "cached", "stale", "demo", "fallback", "unknown"}
_CACHED_WORST = {"cached", "stale", "demo", "fallback"}


def normalize_market_freshness(source: str, raw: Any = None, *, cached: bool = False) -> str:
    freshness = str(raw or "").strip()
    if source in DEMO_SOURCES:
        return "demo"
    if cached or source in CACHED_SOURCES:
        # 缓存命中时载荷里的 "live" 只是写入缓存那一刻的状态，不代表本次
        # 返回仍然实时；只有更差的标签（stale/demo/fallback）可以保留。
        return freshness if freshness in _CACHED_WORST else "cached"
    if freshness in _KNOWN_FRESHNESS:
        return freshness
    if source in FALLBACK_SOURCES:
        return "fallback"
    if source and source != "unknown":
        return "live"
    return "unknown"


def normalize_market_fallback_level(source: str, raw: Any = None, *, cached: bool = False) -> int:
    # 缓存/演示数据一律算最高降级级别，不能被载荷里写入时的 0 覆盖。
    if source in DEMO_SOURCES or cached or source in CACHED_SOURCES:
        return 2
    try:
        if raw is not None and not isinstance(raw, bool):
            return max(0, int(raw))
    except (TypeError, ValueError, OverflowError):
        pass
    if source in FALLBACK_SOURCES:
        return 1
    return 0


def build_market_evidence(payload: dict[str, Any] | None, fallback_source: str = "unknown", *, cached: bool = False) -> dict[str, Any]:
    data = payload or {}
    source = str(data.get("source") or fallback_source or "unknown").strip() or "unknown"
    freshness = normalize_market_freshness(source, data.get("freshness_status") or data.get("freshnessStatus"), cached=cached)
    fallback_level = normalize_market_fallback_level(source, data.get("fallback_level") or data.get("fallbackLevel"), cached=cached)
    as_of = data.get("as_of") or data.get("asOf") or utc_now_iso()
    return {
        "source": source,
        "as_of": as_of,
        "freshness_status": freshness,
        "fallback_level": fallback_level,
        "model_generated": False,
        "degraded": freshness in {"demo", "fallback", "cached", "stale"} or fallback_level >= 1,
        "stale_data": freshness == "stale",
    }


def attach_market_evidence(payload: Any, fallback_source: str = "unknown", *, cached: bool = False) -> Any:
    if not isinstance(payload, dict):
        return payload
    result = dict(payload)
    evidence = build_market_evidence(result, fallback_source=fallback_source, cached=cached)
    result.setdefault("source", evidence["source"])
    result.setdefault("as_of", evidence["as_of"])
    # 缓存/演示命中时，载荷自带的 freshness/fallback_level 是写入时的旧标签
    # （例如 "live"/0），setdefault 会把它留下来，对外伪造成实时数据。
    if cached or evidence["source"] in DEMO_SOURCES or evidence["source"] in CACHED_SOURCES:
        result["freshness_status"] = evidence["freshness_status"]
        result["fallback_level"] = evidence["fallback_level"]
    else:
        result.setdefault("freshness_status", evidence["freshness_status"])
        result.setdefault("fallback_level", evidence["fallback_level"])
    result["evidence"] = evidence
    return result


def attach_financials_evidence(payload: Any, fallback_source: str = "financials", *, cached: bool = False) -> Any:
    if not isinstance(payload, dict):
        return payload
    result = dict(payload)
    inner = result.get("data")
    if isinstance(inner, dict):
        source = str(result.get("source") or inner.get("source") or fallback_source)
        enriched_inner = attach_market_evidence(inner, fallback_source=source, cached=cached)
        result["data"] = enriched_inner
        result["evidence"] = build_market_evidence(enriched_inner, fallback_source=source, cached=cached)
        result.setdefault("source", result["evidence"]["source"])
        result.setdefault("as_of", result["evidence"]["as_of"])
        result.setdefault("freshness_status", result["evidence"]["freshness_status"])
        result.setdefault("fallback_level", result["evidence"]["fallback_level"])
        return result
    return attach_market_evidence(result, fallback_source=fallback_source, cached=cached)
