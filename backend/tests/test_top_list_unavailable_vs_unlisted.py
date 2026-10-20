# -*- coding: utf-8 -*-
"""龙虎榜：取数失败不能被读成"这只票没上榜"。

`fetch_cn_top_list` 在"近期无记录"和"上游 HTTP 失败/回包不可解析/抛异常"
两种情况下都返回 None，路由层原先把两者一律映射成 404「未上榜或数据不可用」：
数据源挂掉时用户看到的是"这只票没上过龙虎榜"（项目规则 2）。
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.market_router import MarketRouterDeps, create_market_router
from backend.tools import tencent_market_providers as tmp


class _Resp:
    def __init__(self, status_code: int, payload=None, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


def test_upstream_http_failure_is_reported_in_diagnostics(monkeypatch):
    monkeypatch.setattr(tmp, "_http_get", lambda *a, **k: _Resp(500))
    diagnostics: dict = {}

    assert tmp.fetch_cn_top_list("600519.SS", include_seats=False, diagnostics=diagnostics) is None
    assert diagnostics["fallback_reason"] == "upstream_error"


def test_upstream_exception_is_reported_in_diagnostics(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(tmp, "_http_get", _boom)
    diagnostics: dict = {}

    assert tmp.fetch_cn_top_list("600519.SS", include_seats=False, diagnostics=diagnostics) is None
    assert diagnostics["fallback_reason"] == "upstream_error"


def test_genuinely_empty_record_list_leaves_no_fallback_reason(monkeypatch):
    """上游正常回空列表：确实没有记录，不能报成取数失败。"""

    def fake_get(url, *a, **k):
        if "datacenter-web" in url:
            return _Resp(200, payload={"result": {"data": []}})
        return _Resp(200, text="var data_tab_1 = [];")

    monkeypatch.setattr(tmp, "_http_get", fake_get)
    diagnostics: dict = {}

    assert tmp.fetch_cn_top_list("600519.SS", include_seats=False, diagnostics=diagnostics) is None
    assert diagnostics == {}


def test_stale_record_is_reported_as_its_own_reason(monkeypatch):
    payload = {"result": {"data": [{"TRADE_DATE": "2020-01-02"}]}}
    monkeypatch.setattr(tmp, "_http_get", lambda *a, **k: _Resp(200, payload=payload))
    diagnostics: dict = {}

    assert tmp.fetch_cn_top_list("600519.SS", include_seats=False, diagnostics=diagnostics) is None
    assert diagnostics["fallback_reason"] == "stale_record"


def test_unparseable_payload_is_reported_as_upstream_error(monkeypatch):
    def fake_get(url, *a, **k):
        if "datacenter-web" in url:
            return _Resp(200, payload={"result": None})
        return _Resp(200, text="var data_tab_1 = null;")

    monkeypatch.setattr(tmp, "_http_get", fake_get)
    diagnostics: dict = {}

    assert tmp.fetch_cn_top_list("600519.SS", include_seats=False, diagnostics=diagnostics) is None
    assert diagnostics["fallback_reason"] == "upstream_error"


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
                logger=logging.getLogger("test_market_router_top_list"),
            )
        )
    )
    return TestClient(app)


def test_route_returns_502_when_upstream_fails(monkeypatch):
    def _fail(ticker, include_seats=True, diagnostics=None):
        diagnostics["fallback_reason"] = "upstream_error"
        return None

    monkeypatch.setattr("backend.tools.tencent_provider.fetch_cn_top_list", _fail)
    response = _build_client().get("/api/stock/top-list/600519.SS")

    assert response.status_code == 502
    assert "不可用" in response.json()["detail"]


def test_route_returns_404_unlisted_when_upstream_has_no_records(monkeypatch):
    def _empty(ticker, include_seats=True, diagnostics=None):
        return None

    monkeypatch.setattr("backend.tools.tencent_provider.fetch_cn_top_list", _empty)
    response = _build_client().get("/api/stock/top-list/600519.SS")

    assert response.status_code == 404
    assert "未上榜" in response.json()["detail"]


def test_route_explains_stale_record_instead_of_claiming_never_listed(monkeypatch):
    def _stale(ticker, include_seats=True, diagnostics=None):
        diagnostics["fallback_reason"] = "stale_record"
        return None

    monkeypatch.setattr("backend.tools.tencent_provider.fetch_cn_top_list", _stale)
    response = _build_client().get("/api/stock/top-list/600519.SS")

    assert response.status_code == 404
    assert "超过90天" in response.json()["detail"]
