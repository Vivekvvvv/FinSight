from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.market_router import MarketRouterDeps, create_market_router


class _NoCache:
    cache = None


def _build_client(*, price_payload=None, financials_payload=None, kline_payload=None) -> TestClient:
    app = FastAPI()
    app.include_router(
        create_market_router(
            MarketRouterDeps(
                get_orchestrator_safe=lambda: None,
                get_stock_price=lambda _ticker: price_payload,
                get_company_news=lambda _ticker: [],
                get_financial_statements=lambda _ticker: financials_payload,
                get_financial_statements_summary=lambda _ticker: {},
                get_stock_historical_data=lambda _ticker, **_kwargs: kline_payload or {"error": "history unavailable"},
                detect_chart_type=None,
                logger=_NoCache(),
            )
        )
    )
    return TestClient(app)


def test_demo_quote_fallback_when_live_quote_missing(monkeypatch):
    monkeypatch.setenv("FINSIGHT_DEMO_MODE", "true")

    with _build_client(price_payload=None) as client:
        response = client.get("/api/quote/NVDA")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["source"] == "demo"
    assert payload["data"]["currentPrice"] == 880.1


def test_demo_kline_fallback_when_history_missing(monkeypatch):
    monkeypatch.setenv("FINSIGHT_DEMO_MODE", "true")

    with _build_client(kline_payload={"error": "history unavailable"}) as client:
        response = client.get("/api/kline/0700.HK")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["source"] == "demo"
    assert data["values"]
    assert data["values"] != _build_client(kline_payload={"error": "history unavailable"}).get("/api/kline/AAPL").json()["data"]["values"]


def test_demo_financials_fallback_when_financials_empty(monkeypatch):
    monkeypatch.setenv("FINSIGHT_DEMO_MODE", "true")

    with _build_client(financials_payload={"error": "financials unavailable"}) as client:
        response = client.get("/api/financials/300750.SZ")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["source"] == "demo"
    assert payload["data"]["currency"] == "CNY"


def test_demo_mode_prefers_demo_quote_for_covered_symbol(monkeypatch):
    monkeypatch.setenv("FINSIGHT_DEMO_MODE", "true")

    with _build_client(price_payload="AAPL Current Price: $123.45 | Change: +1.00 (+0.80%)") as client:
        response = client.get("/api/quote/AAPL")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["source"] == "demo"
    assert data["currentPrice"] == 195.5


def test_live_quote_used_when_demo_mode_disabled(monkeypatch):
    monkeypatch.setenv("FINSIGHT_DEMO_MODE", "false")

    with _build_client(price_payload="AAPL Current Price: $123.45 | Change: +1.00 (+0.80%)") as client:
        response = client.get("/api/quote/AAPL")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["source"] == "tools_bridge"
    assert data["price"] == 123.45
