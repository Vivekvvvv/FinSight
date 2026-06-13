from backend.utils.market_evidence import attach_financials_evidence, attach_market_evidence


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


def test_fallback_market_payload_keeps_live_source_metadata():
    payload = attach_market_evidence({"price": 42, "source": "baostock"}, "baostock")

    assert payload["freshness_status"] == "fallback"
    assert payload["fallback_level"] == 1
    assert payload["evidence"]["source"] == "baostock"


def test_financials_payload_enriches_nested_data():
    payload = attach_financials_evidence({"data": {"trailingPE": 22.5, "source": "demo"}}, "demo")

    assert payload["evidence"]["source"] == "demo"
    assert payload["data"]["evidence"]["freshness_status"] == "demo"
