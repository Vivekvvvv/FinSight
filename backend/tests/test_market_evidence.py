from backend.utils.market_evidence import (
    attach_financials_evidence,
    attach_market_evidence,
    normalize_market_fallback_level,
    normalize_market_freshness,
)


def test_nonlive_market_evidence_without_observation_time_does_not_use_fetch_time():
    for raw, cached in (({"source": "cache"}, False), ({"source": "demo"}, False),
                        ({"source": "baostock"}, False),
                        ({"source": "tencent", "freshness_status": "stale"}, False),
                        ({"source": "tencent", "freshness_status": "unknown"}, False),
                        ({"source": "tencent"}, True)):
        result = attach_market_evidence(raw, cached=cached)
        assert result["as_of"] is None
        assert result["evidence"]["as_of"] is None
    assert attach_market_evidence({"source": "tencent"})["as_of"]
    observed = attach_market_evidence({"source": "cache", "as_of": "2026-01-01"})
    assert observed["as_of"] == "2026-01-01"


def test_failed_status_evidence_does_not_publish_live_prices_or_nested_financials():
    for status in ("error", " Failed ", "unavailable"):
        raw = {"source": "tencent", "status": status, "freshness_status": "live",
               "fallback_level": 0, "price": 100}
        result = attach_market_evidence(raw)
        assert result["freshness_status"] == result["evidence"]["freshness_status"] == "unknown"
        assert result["as_of"] is None
        assert result["fallback_level"] == 1
        nested = attach_financials_evidence({**raw, "data": {"revenue": 100}})
        assert nested["freshness_status"] == nested["data"]["freshness_status"] == "unknown"
        assert nested["data"]["as_of"] is None
        assert nested["evidence"]["degraded"] is True
        assert raw["freshness_status"] == "live"


def test_failed_payload_overrides_preexisting_live_metadata():
    for failure in ({"success": False}, {"error": "unavailable"}):
        payload = attach_market_evidence({**failure, "freshness_status": "live", "fallback_level": 0}, "tencent")
        assert payload["freshness_status"] == "unknown"
        assert payload["fallback_level"] == 1
        assert payload["freshness_status"] == payload["evidence"]["freshness_status"]
        assert payload["as_of"] is None


def test_financial_envelope_propagates_cached_and_demo_status():
    for source, cached, expected in (("tencent", True, "cached"), ("demo", False, "demo")):
        raw = {"freshness_status": "live", "fallback_level": 0, "data": {"source": source, "revenue": 10}}
        payload = attach_financials_evidence(raw, cached=cached)
        assert payload["freshness_status"] == expected
        assert payload["fallback_level"] == 2
        assert payload["data"]["freshness_status"] == expected
        assert raw["freshness_status"] == "live"


def test_zero_fallback_level_takes_precedence_over_legacy_alias():
    payload = attach_market_evidence({"source": "tencent", "fallback_level": 0, "fallbackLevel": 2})
    assert payload["evidence"]["fallback_level"] == 0
    assert payload["evidence"]["degraded"] is False


def test_invalid_fallback_levels_use_source_default():
    for raw in (-1, 3, 1.5, "-1", "999", float("inf")):
        assert normalize_market_fallback_level("baostock", raw) == 1
        payload = attach_market_evidence({"source": "baostock", "fallback_level": raw})
        assert payload["fallback_level"] == payload["evidence"]["fallback_level"] == 1
    assert normalize_market_fallback_level("tencent", "2") == 2


def test_declared_freshness_is_normalized_or_unknown():
    for raw, expected in ((" STALE ", "stale"), ("invalid", "unknown"), (False, "unknown")):
        payload = attach_market_evidence({"source": "tencent", "freshness_status": raw})
        assert payload["freshness_status"] == payload["evidence"]["freshness_status"] == expected
    assert normalize_market_freshness("tencent") == "live"


def test_failed_financial_envelope_cannot_publish_live_nested_data():
    for failure in ({"error": "provider failed"}, {"success": False}):
        raw = {**failure, "freshness_status": "live", "fallback_level": 0, "data": {"revenue": 10}}
        payload = attach_financials_evidence(raw)
        assert payload["evidence"]["freshness_status"] == "unknown"
        assert payload["data"]["freshness_status"] == payload["freshness_status"] == "unknown"
        assert payload["fallback_level"] == 1
        assert payload["data"]["as_of"] is None
        assert "success" not in raw["data"]


def test_financial_metadata_inheritance_and_nested_precedence():
    outer = {"source": "tencent", "freshness_status": "stale", "as_of": "2026-01-01", "fallback_level": 2}
    inherited = attach_financials_evidence({**outer, "data": {"revenue": 10}})
    assert inherited["evidence"]["freshness_status"] == "stale"
    assert inherited["data"]["as_of"] == "2026-01-01"
    nested = {"source": "cache", "freshness_status": "cached", "as_of": "2026-01-02", "fallback_level": 2}
    payload = attach_financials_evidence({**outer, "data": {**nested, "revenue": 10}})
    for key in nested:
        assert payload[key] == payload["data"][key] == payload["evidence"][key] == nested[key]


def test_source_classification_normalizes_case_and_whitespace():
    for source, freshness, level in ((" CACHE ", "cached", 2), ("Demo", "demo", 2), ("YFinance", "fallback", 1)):
        payload = attach_market_evidence({"source": source})
        assert payload["freshness_status"] == freshness
        assert payload["fallback_level"] == level
        assert payload["evidence"]["degraded"] is True


def test_market_fallback_level_ignores_boolean_raw_values():
    assert normalize_market_fallback_level("unknown", True) == 0
    assert normalize_market_fallback_level("baostock", False) == 1


def test_demo_market_payload_gets_demo_evidence():
    payload = attach_market_evidence({"price": 198.3, "source": "demo"}, "demo")

    assert payload["freshness_status"] == "demo"
    assert payload["fallback_level"] == 2
    assert payload["evidence"]["source"] == "demo"
    assert payload["evidence"]["degraded"] is True


def test_cached_market_payload_gets_cached_evidence():
    payload = attach_market_evidence({"price": 101.2}, "cache", cached=True)

    assert payload["source"] == "cache"
    assert payload["freshness_status"] == "cached"
    assert payload["fallback_level"] == 2
    assert payload["evidence"]["freshness_status"] == "cached"


def test_cache_hit_does_not_inherit_live_label_from_stored_payload():
    # 缓存里存的是当初实时抓到的载荷，带着 live/0；本次命中缓存必须降级。
    payload = attach_market_evidence(
        {"price": 101.2, "source": "tools_bridge", "freshness_status": "live", "fallback_level": 0},
        "cache",
        cached=True,
    )

    assert payload["freshness_status"] == "cached"
    assert payload["fallback_level"] == 2
    assert payload["evidence"]["freshness_status"] == "cached"
    assert payload["evidence"]["fallback_level"] == 2
    assert payload["evidence"]["degraded"] is True


def test_cache_hit_keeps_more_degraded_upstream_label():
    assert normalize_market_freshness("cache", "stale", cached=True) == "stale"
    assert normalize_market_freshness("unknown", "live", cached=True) == "cached"
    assert normalize_market_fallback_level("unknown", 0, cached=True) == 2


def test_demo_payload_does_not_inherit_live_label():
    payload = attach_market_evidence(
        {"price": 1.0, "source": "demo", "freshness_status": "live"},
        "demo",
    )

    assert payload["freshness_status"] == "demo"
    assert payload["fallback_level"] == 2


def test_fallback_market_payload_keeps_live_source_metadata():
    payload = attach_market_evidence({"price": 42, "source": "baostock"}, "baostock")

    assert payload["freshness_status"] == "fallback"
    assert payload["fallback_level"] == 1
    assert payload["evidence"]["source"] == "baostock"


def test_financials_payload_enriches_nested_data():
    payload = attach_financials_evidence({"data": {"trailingPE": 22.5, "source": "demo"}}, "demo")

    assert payload["evidence"]["source"] == "demo"
    assert payload["data"]["evidence"]["freshness_status"] == "demo"


def test_failed_financials_payload_is_not_labeled_live():
    # 财报取数失败时 source 仍是 "financials"，normalize 会把它当未知来源
    # 回落成 live；error 载荷必须显式降级。
    payload = attach_market_evidence(
        {"ticker": "AAPL", "error": "获取财报数据失败", "financials": None},
        "financials",
    )

    assert payload["freshness_status"] == "unknown"
    assert payload["fallback_level"] >= 1
    assert payload["evidence"]["degraded"] is True
    # 取数失败没有观测时间，不能补成"现在"。
    assert payload["as_of"] is None
    assert payload["evidence"]["as_of"] is None


def test_success_false_payload_is_not_labeled_live():
    payload = attach_market_evidence({"success": False, "error": "price unavailable"}, "unknown")

    assert payload["freshness_status"] != "live"
    assert payload["evidence"]["degraded"] is True
    assert payload["as_of"] is None


def test_healthy_quote_payload_stays_live():
    payload = attach_market_evidence({"price": 42, "source": "tencent"}, "tencent")

    assert payload["freshness_status"] == "live"
    assert payload["fallback_level"] == 0
    assert payload["evidence"]["degraded"] is False
