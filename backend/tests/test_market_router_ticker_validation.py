import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.market_router import MarketRouterDeps, create_market_router


def _build_client(
    *,
    get_stock_price=None,
    get_company_news=None,
    get_financial_statements=None,
    get_financial_statements_summary=None,
    get_stock_historical_data=None,
    detect_chart_type=None,
) -> TestClient:
    app = FastAPI()
    app.include_router(
        create_market_router(
            MarketRouterDeps(
                get_orchestrator_safe=lambda: None,
                get_stock_price=get_stock_price or (lambda _ticker: {"price": 100.0}),
                get_company_news=get_company_news or (lambda _ticker: []),
                get_financial_statements=get_financial_statements or (lambda _ticker: {}),
                get_financial_statements_summary=get_financial_statements_summary or (lambda _ticker: {}),
                get_stock_historical_data=get_stock_historical_data
                or (lambda _ticker, period="1y", interval="1d": {"kline_data": [], "period": period, "interval": interval}),
                detect_chart_type=detect_chart_type,
                logger=logging.getLogger("test_market_router"),
            )
        )
    )
    return TestClient(app)


@pytest.mark.network
def test_price_endpoint_normalizes_ticker_before_fetch(monkeypatch):
    monkeypatch.setenv("FINSIGHT_DEMO_MODE", "false")
    called: list[str] = []

    def _get_stock_price(ticker: str):
        called.append(ticker)
        return {"price": 123.45}

    client = _build_client(get_stock_price=_get_stock_price)
    response = client.get("/api/stock/price/aapl")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ticker"] == "AAPL"
    assert called == ["AAPL"]


@pytest.mark.parametrize(
    "path",
    [
        "/api/stock/price/GOOGL%20VS%20GOOGLE",
        "/api/stock/kline/GOOGL%20VS%20GOOGLE",
        "/api/stock/news/GOOGL%20VS%20GOOGLE",
        "/api/financials/GOOGL%20VS%20GOOGLE",
        "/api/financials/GOOGL%20VS%20GOOGLE/summary",
    ],
)
def test_market_endpoints_reject_phrase_like_ticker(path: str):
    client = _build_client()
    response = client.get(path)

    assert response.status_code == 400
    detail = str(response.json().get("detail", ""))
    assert "ticker" in detail


def test_kline_endpoint_normalizes_special_symbol():
    called: list[str] = []

    def _get_stock_historical_data(ticker: str, period: str = "1y", interval: str = "1d"):
        called.append(ticker)
        return {"kline_data": [], "period": period, "interval": interval}

    client = _build_client(get_stock_historical_data=_get_stock_historical_data)
    response = client.get("/api/stock/kline/gc=f")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ticker"] == "GC=F"
    assert called == ["GC=F"]


def test_chart_detect_returns_dynamic_ticker_candidates():
    client = _build_client()
    response = client.post(
        "/api/chart/detect",
        json={"query": "compare google and TSLA trend", "ticker": "aapl"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload.get("ticker_candidates"), list)
    assert "AAPL" in payload["ticker_candidates"]
    assert "TSLA" in payload["ticker_candidates"]
    assert payload.get("resolved_ticker") == payload["ticker_candidates"][0]


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"query": "x" * 16_385}, "query"),
        ({"query": "chart trend", "ticker": "A" * 33}, "ticker"),
    ],
)
def test_chart_detect_rejects_oversized_input_before_detector(payload, field):
    calls: list[tuple[str, str | None]] = []

    def _detect(query: str, ticker: str | None):
        calls.append((query, ticker))
        return {}

    client = _build_client(detect_chart_type=_detect)
    response = client.post("/api/chart/detect", json=payload)

    assert response.status_code == 422
    assert field in response.text
    assert calls == []


@pytest.mark.parametrize("path", ["/api/stock/kline/AAPL", "/api/kline/AAPL"])
@pytest.mark.parametrize("parameter", ["period", "interval"])
def test_kline_rejects_oversized_query_parameters_before_fetch(path, parameter):
    calls: list[tuple[str, str, str]] = []

    def _history(ticker: str, period: str = "1y", interval: str = "1d"):
        calls.append((ticker, period, interval))
        return {"kline_data": []}

    client = _build_client(get_stock_historical_data=_history)
    response = client.get(path, params={parameter: "x" * 17})

    assert response.status_code == 422
    assert calls == []


@pytest.mark.parametrize(
    ("path", "parameter", "provider"),
    [
        (
            "/api/stock/top-list/600519.SS/history",
            "start_date",
            "backend.tools.tencent_provider.fetch_cn_top_list_history",
        ),
        (
            "/api/stock/top-list/600519.SS/history",
            "end_date",
            "backend.tools.tencent_provider.fetch_cn_top_list_history",
        ),
        (
            "/api/market/north-flow",
            "date",
            "backend.tools.tencent_provider.fetch_north_flow",
        ),
        (
            "/api/market/historical/AAPL",
            "start",
            "backend.services.historical_data_store.fetch_and_cache_kline",
        ),
        (
            "/api/market/historical/AAPL",
            "end",
            "backend.services.historical_data_store.fetch_and_cache_kline",
        ),
    ],
)
@pytest.mark.parametrize("invalid_date", ["2024/01/01", "2024-01-01&x=1", "2024-99-99"])
def test_market_date_queries_are_rejected_before_provider(
    monkeypatch,
    path,
    parameter,
    provider,
    invalid_date,
):
    calls = []

    def _provider(*args, **kwargs):
        calls.append((args, kwargs))
        return []

    monkeypatch.setattr(provider, _provider)
    client = _build_client()
    response = client.get(path, params={parameter: invalid_date})

    assert response.status_code == 422
    assert calls == []


@pytest.mark.parametrize(
    ("path", "parameters", "provider"),
    [
        (
            "/api/stock/top-list/600519.SS/history",
            {"start_date": "2024-01-02", "end_date": "2024-01-01"},
            "backend.tools.tencent_provider.fetch_cn_top_list_history",
        ),
        (
            "/api/market/historical/AAPL",
            {"start": "2024-01-02", "end": "2024-01-01"},
            "backend.services.historical_data_store.fetch_and_cache_kline",
        ),
    ],
)
def test_market_date_queries_reject_reversed_ranges_before_provider(
    monkeypatch,
    path,
    parameters,
    provider,
):
    calls = []

    def _provider(*args, **kwargs):
        calls.append((args, kwargs))
        return []

    monkeypatch.setattr(provider, _provider)
    response = _build_client().get(path, params=parameters)

    assert response.status_code == 422
    assert calls == []


def test_health_trend_rejects_oversized_source_before_storage(monkeypatch):
    from backend.services import monitoring_storage

    def _unexpected_storage():
        raise AssertionError("oversized source must be rejected before storage access")

    monkeypatch.setattr(monitoring_storage, "get_storage", _unexpected_storage)
    response = _build_client().get(
        "/api/system/health/trend",
        params={"source": "x" * 129},
    )

    assert response.status_code == 422
