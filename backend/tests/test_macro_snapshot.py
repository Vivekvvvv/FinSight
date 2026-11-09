# -*- coding: utf-8 -*-

from backend.dashboard.data_service import fetch_macro_snapshot


def test_unemployment_values_outside_percentage_bounds_are_unavailable(monkeypatch):
    import backend.tools.macro as tools
    monkeypatch.setattr(tools, "get_market_sentiment", lambda: "")
    for value in (-1, 101):
        monkeypatch.setattr(tools, "get_fred_data", lambda: {"unemployment": value})
        result = fetch_macro_snapshot()
        assert result["unemployment"] is None
        assert result["status"] == "unavailable"


def test_out_of_range_fear_greed_values_are_unavailable_instead_of_clamped(monkeypatch):
    import backend.tools.macro as tools
    monkeypatch.setattr(tools, "get_fred_data", lambda: {})
    for text in ("Fear & Greed Index: 999", "Fear & Greed Index: -5"):
        monkeypatch.setattr(tools, "get_market_sentiment", lambda: text)
        result = fetch_macro_snapshot()
        assert result["fear_greed_index"] is None
        assert result["status"] == "unavailable"


def test_failed_fred_payload_cannot_be_presented_as_available_macro_data(monkeypatch):
    import backend.tools.macro as tools
    monkeypatch.setattr(tools, "get_market_sentiment", lambda: "")
    for failure in ({"success": False}, {"error": "offline"}, {"status": " Failed "}):
        monkeypatch.setattr(tools, "get_fred_data", lambda: {"fed_rate": 99.0, **failure})
        result = fetch_macro_snapshot()
        assert result["fed_rate"] is None
        assert result["status"] == "unavailable"


def test_fetch_macro_snapshot_parses_fear_greed_and_fred(monkeypatch):
    import backend.tools.macro as macro_tools

    monkeypatch.setattr(
        macro_tools,
        "get_market_sentiment",
        lambda: "CNN Fear & Greed Index: 62 (Greed)",
    )
    monkeypatch.setattr(
        macro_tools,
        "get_fred_data",
        lambda: {
            "fed_rate": 5.25,
            "cpi": 3.2,
            "unemployment": 4.0,
            "gdp_growth": 2.1,
            "treasury_10y": 4.15,
            "yield_spread": -0.25,
            "as_of": "2026-02-18T00:00:00+00:00",
        },
    )

    payload = fetch_macro_snapshot()

    assert payload["status"] == "ok"
    assert payload["fear_greed_index"] == 62.0
    assert payload["fear_greed_label"] == "greed"
    assert payload["fed_rate"] == 5.25
    assert payload["cpi"] == 3.2
    assert payload["unemployment"] == 4.0
    assert payload["as_of"] == "2026-02-18T00:00:00+00:00"


def test_fetch_macro_snapshot_gracefully_handles_tool_failures(monkeypatch):
    import backend.tools.macro as macro_tools

    def _raise_sentiment():
        raise RuntimeError("sentiment down")

    def _raise_fred():
        raise RuntimeError("fred down")

    monkeypatch.setattr(macro_tools, "get_market_sentiment", _raise_sentiment)
    monkeypatch.setattr(macro_tools, "get_fred_data", _raise_fred)

    payload = fetch_macro_snapshot()

    assert payload["status"] == "unavailable"
    assert payload["fear_greed_index"] is None
    assert payload["fed_rate"] is None
    assert isinstance(payload.get("as_of"), str) and payload["as_of"]
