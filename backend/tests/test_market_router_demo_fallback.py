from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.market_router import MarketRouterDeps, create_market_router


def test_invalid_us_chart_payload_does_not_hide_valid_shared_history(monkeypatch):
    monkeypatch.setenv("FINSIGHT_DEMO_MODE", "false")
    for marker in ({"success": False}, {"error": "offline"}, {"status": " Failed "}, {"symbol": "MSFT"}):
        with _build_client(kline_payload={"kline_data": [{"close": 100}]},
                           us_intraday=lambda ticker: {"line_data": [{"value": 200}], **marker}) as client:
            response = client.get("/api/kline/AAPL")
        assert response.status_code == 200
        assert response.json()["data"].get("kline_data") == [{"close": 100}]


def test_failed_or_unrelated_cn_kline_does_not_block_shared_history(monkeypatch):
    monkeypatch.setenv("FINSIGHT_DEMO_MODE", "false")
    for marker in ({"success": False}, {"error": "offline"}, {"status": " Failed "}, {"symbol": "000858.SZ"}):
        monkeypatch.setattr("backend.api.market_router.fetch_cn_kline",
                            lambda ticker, **kwargs: {"values": [[100, 100, 90, 110]], **marker})
        with _build_client(kline_payload={"kline_data": [{"close": 200}]}) as client:
            response = client.get("/api/kline/600519.SS")
        assert response.status_code == 200
        assert response.json()["data"].get("kline_data") == [{"close": 200}]


def test_direct_quotes_require_positive_prices_before_blocking_shared_fallback(monkeypatch):
    monkeypatch.setenv("FINSIGHT_DEMO_MODE", "false")
    for invalid in (None, 0, -1, True, "bad"):
        monkeypatch.setattr("backend.api.market_router.fetch_cn_quote",
                            lambda ticker: {"currentPrice": invalid})
        with _build_client(price_payload={"price": 100}) as client:
            response = client.get("/api/quote/600519.SS")
        assert response.json()["data"].get("price") == 100
        with _build_client(price_payload={"price": 100}, us_quote=lambda ticker: {"price": invalid}) as client:
            response = client.get("/api/quote/AAPL")
        assert response.json()["data"]["price"] == 100


def test_invalid_us_quote_payload_does_not_hide_valid_shared_quote(monkeypatch):
    monkeypatch.setenv("FINSIGHT_DEMO_MODE", "false")
    for marker in ({"success": False}, {"error": "offline"}, {"status": " Failed "}, {"symbol": "MSFT"}):
        with _build_client(price_payload={"price": 100}, us_quote=lambda ticker: {"price": 200, **marker}) as client:
            response = client.get("/api/quote/AAPL")
        assert response.status_code == 200
        assert response.json()["data"]["price"] == 100


def test_invalid_cn_quote_payload_does_not_hide_valid_shared_quote(monkeypatch):
    monkeypatch.setenv("FINSIGHT_DEMO_MODE", "false")
    for marker in ({"success": False}, {"error": "offline"}, {"status": " Failed "}, {"ticker": "000858.SZ"}):
        monkeypatch.setattr("backend.api.market_router.fetch_cn_quote",
                            lambda ticker: {"currentPrice": 200, **marker})
        with _build_client(price_payload={"price": 100}) as client:
            response = client.get("/api/quote/600519.SS")
        assert response.status_code == 200
        assert response.json()["data"].get("price") == 100


def test_live_intraday_failure_or_wrong_stock_cannot_enter_response_or_cache(monkeypatch):
    monkeypatch.setenv("FINSIGHT_DEMO_MODE", "false")
    for marker in ({"success": False}, {"error": "offline"}, {"status": " Failed "}, {"ticker": "000858.SZ"}):
        monkeypatch.setattr("backend.api.market_router.fetch_cn_intraday",
                            lambda ticker: {"data": [{"price": 200}], **marker})
        writes = []
        orchestrator = _Orchestrator(None)
        orchestrator.cache.set = lambda *args, **kwargs: writes.append(args)
        with _build_client(orchestrator=orchestrator) as client:
            response = client.get("/api/stock/intraday/600519.SS")
        assert response.status_code == 502
        assert writes == []


def test_failed_or_unrelated_cached_intraday_uses_valid_current_source(monkeypatch):
    monkeypatch.setenv("FINSIGHT_DEMO_MODE", "false")
    current = {"ticker": "600519.SS", "data": [{"price": 100}]}
    monkeypatch.setattr("backend.api.market_router.fetch_cn_intraday", lambda ticker: current)
    for failure in ({"error": "offline"}, {"success": False}, {"status": " Failed "}, {"ticker": "000858.SZ"}):
        orchestrator = _Orchestrator({"data": [{"price": 200}], **failure})
        writes = []
        orchestrator.cache.set = lambda *args, **kwargs: writes.append(args)
        with _build_client(orchestrator=orchestrator) as client:
            response = client.get("/api/stock/intraday/600519.SS")
        assert response.status_code == 200
        assert response.json()["data"]["data"] == [{"price": 100}]
        assert response.json()["cached"] is False
        assert len(writes) == 1


def test_intraday_failures_return_502_instead_of_success_shaped_errors(monkeypatch):
    monkeypatch.setenv("FINSIGHT_DEMO_MODE", "false")
    monkeypatch.setattr("backend.api.market_router.fetch_cn_intraday", lambda ticker: None)
    for ticker in ("AAPL", "600519.SS"):
        with _build_client() as client:
            response = client.get("/api/stock/intraday/" + ticker)
        assert response.status_code == 502
        assert response.json()["detail"] == "Intraday data unavailable"


def test_cached_and_live_kline_must_match_the_route_stock(monkeypatch):
    monkeypatch.setenv("FINSIGHT_DEMO_MODE", "false")
    for raw in ({"ticker": "MSFT", "kline_data": [{"close": 200}]},
                {"data": {"symbol": "MSFT", "kline_data": [{"close": 200}]}}):
        with _build_client(kline_payload=raw) as client:
            assert client.get("/api/kline/AAPL").status_code == 502
        orchestrator = _Orchestrator(raw)
        orchestrator.cache.set = lambda *args, **kwargs: None
        with _build_client(kline_payload={"ticker": "AAPL", "kline_data": [{"close": 100}]},
                           orchestrator=orchestrator) as client:
            response = client.get("/api/kline/AAPL")
        assert response.status_code == 200
        assert response.json()["data"]["kline_data"] == [{"close": 100}]
        assert response.json()["cached"] is False


def test_financial_route_rejects_data_explicitly_labeled_for_another_stock(monkeypatch):
    monkeypatch.setenv("FINSIGHT_DEMO_MODE", "false")
    for raw in ({"ticker": "MSFT", "data": {"revenue": 100}},
                {"data": {"symbol": "MSFT", "revenue": 100}}):
        with _build_client(financials_payload=raw) as client:
            assert client.get("/api/financials/AAPL").status_code == 502
    with _build_client(financials_payload={"ticker": " aapl ", "data": {"revenue": 100}}) as client:
        assert client.get("/api/financials/AAPL").status_code == 200


def test_market_payload_identity_checks_cover_every_nested_envelope():
    from backend.api.market_router_helpers import _has_usable_payload
    for raw in ({"symbol": "MSFT", "kline_data": [100]},
                {"ticker": "MSFT", "data": {"ticker": "AAPL", "revenue": 100}},
                {"data": {"symbol": "MSFT", "revenue": 100}}):
        assert not _has_usable_payload(raw, expected_ticker="AAPL")
    assert _has_usable_payload({"symbol": " aapl ", "data": {"ticker": "AAPL", "revenue": 100}},
                               expected_ticker=" aapl ")


def test_failed_cached_kline_is_replaced_by_valid_history(monkeypatch):
    monkeypatch.setenv("FINSIGHT_DEMO_MODE", "false")
    for failure in ({"error": "offline"}, {"success": False}, {"status": " Failed "}):
        orchestrator = _Orchestrator({"kline_data": [{"close": 200}], **failure})
        writes = []
        orchestrator.cache.set = lambda *args, **kwargs: writes.append(args)
        with _build_client(kline_payload={"kline_data": [{"close": 100}]}, orchestrator=orchestrator) as client:
            response = client.get("/api/kline/AAPL")
        assert response.status_code == 200
        assert response.json()["data"]["kline_data"] == [{"close": 100}]
        assert response.json()["cached"] is False
        assert len(writes) == 1


def test_failed_kline_returns_502_without_caching_provider_errors(monkeypatch):
    monkeypatch.setenv("FINSIGHT_DEMO_MODE", "false")
    for raw in ({"error": "offline"}, {"success": False, "kline_data": [{"close": 100}]},
                {"status": " Failed ", "kline_data": [{"close": 100}]}):
        writes = []
        orchestrator = _Orchestrator(None)
        orchestrator.cache.set = lambda *args, **kwargs: writes.append(args)
        with _build_client(kline_payload=raw, orchestrator=orchestrator) as client:
            response = client.get("/api/kline/AAPL")
        assert response.status_code == 502
        assert response.json()["detail"] == "Kline data unavailable"
        assert writes == []


def test_cached_quote_identity_must_match_the_requested_stock(monkeypatch):
    monkeypatch.setenv("FINSIGHT_DEMO_MODE", "false")
    for raw in ({"ticker": "MSFT", "price": 200},
                {"data": {"symbol": "MSFT", "price": 200}}):
        orchestrator = _Orchestrator(raw)
        orchestrator.cache.set = lambda *args, **kwargs: None
        with _build_client(price_payload={"price": 100}, orchestrator=orchestrator) as client:
            response = client.get("/api/quote/AAPL")
        assert response.status_code == 200
        assert response.json()["data"]["price"] == 100
        assert response.json().get("cached") is not True


def test_missing_quote_returns_502_and_does_not_cache_failed_raw_payload(monkeypatch):
    monkeypatch.setenv("FINSIGHT_DEMO_MODE", "false")
    monkeypatch.setattr("backend.utils.quote.fallback_quote_yfinance", lambda ticker: None)
    for raw in (None, {"error": "offline"}, {"status": " Failed ", "price": 200}):
        writes = []
        orchestrator = _Orchestrator(None)
        orchestrator.cache.set = lambda *args, **kwargs: writes.append(args)
        with _build_client(price_payload=raw, orchestrator=orchestrator) as client:
            response = client.get("/api/quote/AAPL")
        assert response.status_code == 502
        assert response.json()["detail"] == "无法获取 AAPL 价格数据"
        assert writes == []


def test_failed_financials_provider_returns_502_without_success_shaped_data(monkeypatch):
    monkeypatch.setenv("FINSIGHT_DEMO_MODE", "false")
    for failure in ({"error": "offline"}, {"success": False}, {"status": " Failed "},
                    {"data": {"success": False, "revenue": 100}}):
        with _build_client(financials_payload=failure) as client:
            response = client.get("/api/financials/AAPL")
        assert response.status_code == 502
        assert response.json()["detail"] == "无法获取 AAPL 财务数据"


def test_market_payload_availability_rejects_failure_flags_in_each_envelope():
    from backend.api.market_router_helpers import _has_usable_payload
    for failure in ({"success": False}, {"status": " Failed "}, {"status": "UNAVAILABLE"}, {"error": "bad"}):
        assert not _has_usable_payload({**failure, "revenue": 100})
        assert not _has_usable_payload({"data": {"data": {**failure, "revenue": 100}}})
    assert _has_usable_payload({"data": {"revenue": 100}})


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
