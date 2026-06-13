from backend.services.data_source_status import get_data_source_status


def test_data_source_status_reports_market_components(monkeypatch):
    monkeypatch.delenv("FINSIGHT_DEMO_MODE", raising=False)
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_COMPATIBLE_API_KEY", raising=False)
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("API_AUTH_KEYS", raising=False)

    result = get_data_source_status()

    assert result["success"] is True
    keys = {item["key"] for item in result["components"]}
    assert {"market_us", "market_cn", "market_hk", "llm", "rag", "auth"} <= keys
    assert result["overall_status"] in {"fallback_ready", "needs_config"}
    assert "OPENAI_COMPATIBLE_API_KEY" in result["missing_services"]


def test_data_source_status_demo_mode(monkeypatch):
    monkeypatch.setenv("FINSIGHT_DEMO_MODE", "true")

    result = get_data_source_status()

    assert result["demo_mode"] is True
    assert result["overall_status"] == "demo"
    assert all(item["status"] in {"demo", "fallback_ready"} for item in result["components"])
