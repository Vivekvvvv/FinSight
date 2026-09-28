# -*- coding: utf-8 -*-
"""ApiMetricsMiddleware：alerts.yml 的 HighAPIErrorRate /
SlowAPIResponse / HighActiveRequests 三条告警全靠它喂数。
关键约束：endpoint 必须是路由模板（scope["route"].path），
不能用 request.url.path——路径参数会让序列基数无限膨胀。"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    from backend.api.metrics_middleware import ApiMetricsMiddleware

    app = FastAPI()
    app.add_middleware(ApiMetricsMiddleware)

    @app.get("/api/mtw/quote/{ticker}")
    def quote(ticker: str):
        return {"ticker": ticker}

    @app.get("/api/mtw/slow")
    def slow():
        return {"ok": True}

    @app.get("/api/mtw/boom")
    def boom():
        raise RuntimeError("handler exploded")

    @app.get("/api/mtw/http500")
    def http500():
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=500, content={"detail": "handled"})

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _sample(name: str, labels: dict) -> float | None:
    from backend.monitoring.prometheus_exporter import registry

    return registry.get_sample_value(name, labels)


def test_records_request_with_route_template_label(client):
    client.get("/api/mtw/quote/600519.SS")

    # 关键断言：endpoint 是路由模板而非实际 URL——路径参数不得进标签
    assert _sample(
        "finsight_api_requests_total",
        {"method": "GET", "endpoint": "/api/mtw/quote/{ticker}", "status_code": "200"},
    ) == 1.0
    assert _sample(
        "finsight_api_requests_total",
        {"method": "GET", "endpoint": "/api/mtw/quote/600519.SS", "status_code": "200"},
    ) is None


def test_records_duration_histogram(client):
    client.get("/api/mtw/slow")

    assert _sample(
        "finsight_api_request_duration_seconds_count",
        {"method": "GET", "endpoint": "/api/mtw/slow"},
    ) == 1.0


def test_active_requests_returns_to_zero(client):
    from backend.monitoring.prometheus_exporter import active_requests

    client.get("/api/mtw/quote/MSFT")
    assert active_requests._value.get() == 0.0


def test_escaped_exception_records_error_type(client):
    """handler 异常逃逸到本层（ServerErrorMiddleware 在最外兜底 500），
    error_type 记真实异常类名。"""
    resp = client.get("/api/mtw/boom")

    assert resp.status_code == 500
    assert _sample(
        "finsight_api_errors_total",
        {"method": "GET", "endpoint": "/api/mtw/boom", "error_type": "RuntimeError"},
    ) == 1.0


def test_handled_500_records_http_5xx(client):
    """框架内处理的 500 响应（无异常逃逸）按状态码补记 http_5xx——
    否则此类 500 不进 errors_total，HighAPIErrorRate 假阴性。"""
    resp = client.get("/api/mtw/http500")

    assert resp.status_code == 500
    assert _sample(
        "finsight_api_errors_total",
        {"method": "GET", "endpoint": "/api/mtw/http500", "error_type": "http_5xx"},
    ) == 1.0


def test_unmatched_path_uses_bounded_label(client):
    client.get("/definitely/not/a/route/" + "x" * 50)

    assert _sample(
        "finsight_api_requests_total",
        {"method": "GET", "endpoint": "__unmatched__", "status_code": "404"},
    ) == 1.0


def test_non_http_scope_passthrough():
    """websocket/lifespan scope 直通，不记指标、不炸。"""
    import asyncio

    from backend.api.metrics_middleware import ApiMetricsMiddleware

    called = []

    async def app(scope, receive, send):
        called.append(scope["type"])

    mw = ApiMetricsMiddleware(app)
    asyncio.run(mw({"type": "lifespan"}, lambda: None, lambda m: None))
    assert called == ["lifespan"]
