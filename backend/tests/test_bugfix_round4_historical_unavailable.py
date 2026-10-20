# -*- coding: utf-8 -*-
"""历史K线取数失败不能被读成"这只票没有历史数据"。

`fetch_and_cache_kline` 在两个失败分支（降级源返回 {"error": ...}、降级源抛异常）
都返回 `[]`，与"标的确实没有历史数据"同形；`/api/market/historical/{ticker}`
于是回 200 + bars:0，前端只能显示"暂无历史数据"（项目规则 2）。
"""
from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.market_router import MarketRouterDeps, create_market_router
from backend.services import historical_data_store as store


@pytest.fixture()
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_DB_PATH", str(tmp_path / "kline.db"))
    monkeypatch.setattr(store, "_table_ready", False)
    monkeypatch.setattr(store, "_fetch_baostock", lambda *a, **k: [])
    return store


def test_upstream_error_is_reported_in_diagnostics(isolated_store, monkeypatch):
    monkeypatch.setattr(
        "backend.tools.get_stock_historical_data",
        lambda *a, **k: {"error": "All data sources failed."},
    )
    diagnostics: dict = {}

    rows = isolated_store.fetch_and_cache_kline(
        "600519.SS", "2026-01-01", "2026-12-31", "qfq", diagnostics
    )

    assert rows == []
    assert diagnostics["fallback_reason"] == "upstream_error"


def test_fallback_exception_is_reported_in_diagnostics(isolated_store, monkeypatch):
    monkeypatch.setattr(
        "backend.tools.get_stock_historical_data",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("upstream exploded")),
    )
    diagnostics: dict = {}

    rows = isolated_store.fetch_and_cache_kline(
        "600519.SS", "2026-01-01", "2026-12-31", "qfq", diagnostics
    )

    assert rows == []
    assert diagnostics["fallback_reason"] == "fallback_failed"


def test_genuinely_empty_history_leaves_no_fallback_reason(isolated_store, monkeypatch):
    """真拉到数据、只是区间内没有 bar：不能报成取数失败。"""
    monkeypatch.setattr(
        "backend.tools.get_stock_historical_data", lambda *a, **k: {"kline_data": []}
    )
    diagnostics: dict = {}

    rows = isolated_store.fetch_and_cache_kline(
        "600519.SS", "2026-01-01", "2026-12-31", "qfq", diagnostics
    )

    assert rows == []
    assert diagnostics == {}


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(
        create_market_router(
            MarketRouterDeps(
                get_orchestrator_safe=lambda: None,
                get_stock_price=lambda _ticker: {"price": 100.0},
                get_company_news=lambda _ticker: [],
                get_financial_statements=lambda _ticker: {},
                get_financial_statements_summary=lambda _ticker: {},
                get_stock_historical_data=lambda _ticker, period="1y", interval="1d": {"kline_data": []},
                detect_chart_type=None,
                logger=logging.getLogger("test_market_router_round4"),
            )
        )
    )
    return TestClient(app)


def test_endpoint_surfaces_fallback_reason_when_bars_empty(monkeypatch):
    def _fail(**kwargs):
        kwargs["diagnostics"]["fallback_reason"] = "upstream_error"
        return []

    monkeypatch.setattr(store, "fetch_and_cache_kline", _fail)
    response = _build_client().get("/api/market/historical/600519.SS")

    assert response.status_code == 200
    payload = response.json()
    assert payload["bars"] == 0
    assert payload["fallback_reason"] == "upstream_error"


def test_endpoint_omits_fallback_reason_for_genuine_empty(monkeypatch):
    monkeypatch.setattr(store, "fetch_and_cache_kline", lambda **kwargs: [])
    response = _build_client().get("/api/market/historical/600519.SS")

    assert response.status_code == 200
    payload = response.json()
    assert payload["bars"] == 0
    assert "fallback_reason" not in payload
