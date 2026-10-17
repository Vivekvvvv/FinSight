from backend.utils.market_evidence import (
    attach_financials_evidence,
    attach_market_evidence,
    normalize_market_fallback_level,
    normalize_market_freshness,
)


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
