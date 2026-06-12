# -*- coding: utf-8 -*-
"""Demo Mode smoke tests."""

from fastapi.testclient import TestClient

from backend.api.demo_router import demo_router
from backend.demo_mode import (
    demo_financials,
    demo_kline,
    demo_notes,
    demo_portfolio_summary,
    demo_quote,
    demo_reports,
    demo_status,
    demo_timeline,
    demo_today_workspace,
)


def test_demo_status_reports_mode_and_missing_services(monkeypatch):
    monkeypatch.setenv("FINSIGHT_DEMO_MODE", "true")
    monkeypatch.delenv("FMP_API_KEY", raising=False)

    status = demo_status()

    assert status["success"] is True
    assert status["demo_mode"] is True
    assert status["data_source"] == "demo"
    assert status["overall_status"] == "demo"
    assert "FMP_API_KEY" in status["missing_services"]
    assert {item["key"] for item in status["components"]} == {"market_data", "llm", "auth"}
    assert all(item["status"] == "demo" for item in status["components"])


def test_demo_status_api():
    app = __import__("fastapi").FastAPI()
    app.include_router(demo_router)

    with TestClient(app) as client:
        response = client.get("/api/demo/status")

    assert response.status_code == 200
    assert response.json()["success"] is True


def test_demo_status_reports_market_fallback_without_paid_key(monkeypatch):
    monkeypatch.setenv("FINSIGHT_DEMO_MODE", "false")
    for name in ("FMP_API_KEY", "ALPHA_VANTAGE_API_KEY", "FINNHUB_API_KEY", "TWELVE_DATA_API_KEY", "EODHD_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    status = demo_status()
    market = next(item for item in status["components"] if item["key"] == "market_data")

    assert market["status"] == "fallback_ready"
    assert "BaoStock" in market["detail"]


def test_demo_core_payloads_are_non_empty():
    session_id = "public:demo:thread"

    portfolio = demo_portfolio_summary(session_id)
    today = demo_today_workspace(session_id)
    reports = demo_reports(session_id)
    notes = demo_notes(session_id, "demo_user")
    timeline = demo_timeline("AAPL", session_id)

    assert portfolio["count"] >= 2
    assert today["portfolio_snapshot"]["position_count"] >= 2
    assert len(reports) >= 2
    assert len(notes) >= 2
    assert len(timeline) >= 2
    assert today["freshness_status"] == "demo"


def test_demo_market_payloads_are_symbol_specific():
    aapl_quote = demo_quote("AAPL")
    nvda_quote = demo_quote("NVDA")
    msft_quote = demo_quote("MSFT")

    assert aapl_quote and nvda_quote and msft_quote
    assert len({aapl_quote["currentPrice"], nvda_quote["currentPrice"], msft_quote["currentPrice"]}) == 3
    assert aapl_quote["source"] == "demo"
    assert aapl_quote["freshness_status"] == "demo"
    assert aapl_quote["fallback_level"] == 2

    aapl_kline = demo_kline("AAPL")
    nvda_kline = demo_kline("NVDA")
    hk_kline = demo_kline("0700.HK")
    cn_kline = demo_kline("600519.SS")

    assert aapl_kline and nvda_kline and hk_kline and cn_kline
    assert aapl_kline["values"] != nvda_kline["values"]
    assert hk_kline["values"] != cn_kline["values"]
    assert len(aapl_kline["kline_data"]) >= 10
    assert aapl_kline["source"] == "demo"


def test_demo_financials_cover_cn_and_hk_symbols():
    hk = demo_financials("0700.HK")
    cn = demo_financials("300750.SZ")

    assert hk and cn
    assert hk["data"]["currency"] == "HKD"
    assert cn["data"]["currency"] == "CNY"
    assert hk["data"]["trailingPE"] != cn["data"]["trailingPE"]
