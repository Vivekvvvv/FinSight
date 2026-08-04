from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.market_router import MarketRouterDeps, create_market_router


class _NoCache:
    cache = None


class _Logger:
    def info(self, *_args, **_kwargs):
        return None


class _Cache:
    def __init__(self, payload):
        self.payload = payload

    def get(self, _key):
        return self.payload


class _Orchestrator:
    def __init__(self, payload):
        self.cache = _Cache(payload)


def _build_client(
    *,
    price_payload=None,
    financials_payload=None,
    kline_payload=None,
    us_quote=None,
    us_intraday=None,
    orchestrator=None,
) -> TestClient:
    app = FastAPI()
    app.include_router(
        create_market_router(
            MarketRouterDeps(
                get_orchestrator_safe=lambda: orchestrator,
                get_stock_price=lambda _ticker: price_payload,
                get_company_news=lambda _ticker: [],
                get_financial_statements=lambda _ticker: financials_payload,
                get_financial_statements_summary=lambda _ticker: {},
                get_stock_historical_data=lambda _ticker, **_kwargs: kline_payload or {"error": "history unavailable"},
                detect_chart_type=None,
                logger=_Logger(),
                get_us_quote=us_quote,
                get_us_intraday=us_intraday,
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


def test_cn_quote_uses_baostock_when_demo_disabled(monkeypatch):
    monkeypatch.setenv("FINSIGHT_DEMO_MODE", "false")
    monkeypatch.setattr(
        "backend.api.market_router.fetch_cn_quote",
        lambda _ticker: {
            "currentPrice": 1688.0,
            "source": "baostock",
            "freshness_status": "live",
            "fallback_level": 1,
        },
    )

    with _build_client(price_payload=None) as client:
        response = client.get("/api/quote/600519.SS")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["source"] == "baostock"
    assert data["currentPrice"] == 1688.0
    assert data["fallback_level"] == 1


def test_cn_kline_uses_baostock_when_demo_disabled(monkeypatch):
    monkeypatch.setenv("FINSIGHT_DEMO_MODE", "false")
    monkeypatch.setattr(
        "backend.api.market_router.fetch_cn_kline",
        lambda _ticker, **_kwargs: {
            "dates": ["2026-06-10", "2026-06-11"],
            "values": [[10, 11, 9, 12], [11, 12, 10, 13]],
            "kline_data": [],
            "source": "baostock",
            "freshness_status": "live",
            "fallback_level": 1,
        },
    )

    with _build_client(kline_payload={"error": "should not be used"}) as client:
        response = client.get("/api/kline/300750.SZ")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["source"] == "baostock"
    assert data["values"][0] == [10, 11, 9, 12]


def test_us_quote_uses_nasdaq_before_legacy_chain(monkeypatch):
    monkeypatch.setenv("FINSIGHT_DEMO_MODE", "false")
    us_quote = lambda _ticker: {
            "name": "Western Digital Corporation",
            "price": 539.02,
            "change": 11.8,
            "change_percent": 2.24,
            "volume": 8_279_896,
            "source": "nasdaq_quote",
        }

    with _build_client(price_payload=None, us_quote=us_quote) as client:
        response = client.get("/api/quote/WDC")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["source"] == "nasdaq_quote"
    assert data["price"] == 539.02


def test_cached_quote_preserves_extended_market_fields(monkeypatch):
    monkeypatch.setenv("FINSIGHT_DEMO_MODE", "false")
    cached_quote = {
        "name": "Western Digital Corporation",
        "price": "539.02",
        "change": "11.8",
        "change_percent": "2.24",
        "volume": 8_279_896,
        "market_cap": 188_000_000_000,
        "source": "nasdaq_quote",
    }

    with _build_client(orchestrator=_Orchestrator(cached_quote)) as client:
        response = client.get("/api/quote/WDC")

    assert response.status_code == 200
    payload = response.json()
    assert payload["cached"] is True
    assert payload["data"]["price"] == 539.02
    assert payload["data"]["name"] == "Western Digital Corporation"
    assert payload["data"]["volume"] == 8_279_896
    assert payload["data"]["market_cap"] == 188_000_000_000


def test_us_kline_uses_real_nasdaq_intraday_without_fake_ohlc(monkeypatch):
    monkeypatch.setenv("FINSIGHT_DEMO_MODE", "false")
    us_intraday = lambda _ticker: {
            "symbol": "WDC",
            "line_data": [
                {"time": "2026-08-04T13:30:00+00:00", "value": 538.5},
                {"time": "2026-08-04T13:31:00+00:00", "value": 539.02},
            ],
            "chart_kind": "intraday_line",
            "source": "nasdaq_intraday",
        }

    with _build_client(kline_payload={"error": "legacy chain should not be used"}, us_intraday=us_intraday) as client:
        response = client.get("/api/kline/WDC")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["chart_kind"] == "intraday_line"
    assert data["line_data"][1]["value"] == 539.02
    assert "open" not in data["line_data"][0]
