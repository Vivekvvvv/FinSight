from backend.services.data_source_status import get_data_source_status


def test_data_source_status_reports_market_components(monkeypatch):
    monkeypatch.delenv("FINSIGHT_DEMO_MODE", raising=False)
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_COMPATIBLE_API_KEY", raising=False)
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("API_AUTH_KEYS", raising=False)

    result = get_data_source_status()

    assert result["success"] is True
    keys = {item["key"] for item in result["components"]}
    assert {"market_us", "stock_screener", "market_cn", "market_hk", "llm", "rag", "auth"} <= keys
    assert result["overall_status"] in {"fallback_ready", "needs_config"}
    assert "OPENAI_COMPATIBLE_API_KEY" in result["missing_services"]


def test_data_source_status_separates_quote_key_from_screener_key(monkeypatch):
    monkeypatch.delenv("FINSIGHT_DEMO_MODE", raising=False)
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "demo-alpha")
    monkeypatch.delenv("FMP_API_KEY", raising=False)

    result = get_data_source_status()
    components = {item["key"]: item for item in result["components"]}

    assert components["market_us"]["status"] == "live_ready"
    assert components["stock_screener"]["status"] == "fallback_ready"
    assert "FMP_API_KEY" in str(components["stock_screener"]["required_action"])


def test_data_source_status_demo_mode(monkeypatch):
    monkeypatch.setenv("FINSIGHT_DEMO_MODE", "true")

    result = get_data_source_status()

    assert result["demo_mode"] is True
    assert result["overall_status"] == "demo"
    assert all(item["status"] in {"demo", "fallback_ready"} for item in result["components"])
