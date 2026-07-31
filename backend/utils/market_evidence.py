from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


DEMO_SOURCES = {"demo", "static_market_demo"}
CACHED_SOURCES = {"cache", "cached"}
FALLBACK_SOURCES = {"baostock", "yfinance", "eastmoney"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_market_freshness(source: str, raw: Any = None, *, cached: bool = False) -> str:
    freshness = str(raw or "").strip()
    if freshness in {"live", "delayed_15min", "cached", "stale", "demo", "fallback", "unknown"}:
        return freshness
    if source in DEMO_SOURCES:
        return "demo"
    if cached or source in CACHED_SOURCES:
        return "cached"
    if source in FALLBACK_SOURCES:
        return "fallback"
    if source and source != "unknown":
        return "live"
    return "unknown"


def normalize_market_fallback_level(source: str, raw: Any = None, *, cached: bool = False) -> int:
    try:
        if raw is not None:
            return max(0, int(raw))
    except (TypeError, ValueError, OverflowError):
        pass
    if source in DEMO_SOURCES or cached or source in CACHED_SOURCES:
        return 2
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
