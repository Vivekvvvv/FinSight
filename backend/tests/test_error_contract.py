# -*- coding: utf-8 -*-
"""F 类回归（docs/BUG_AUDIT_2026-07-04.md）：路由层内部异常不得压成 200。

历史行为：today / research-notes 的宽 except 返回 200 + {"success": False}
（today 还带整套空骨架），前端把它当正常数据渲染，后端故障对用户与监控
完全不可见。修复后统一 raise HTTPException(500)，与同文件 semantic-search /
vectorize 端点的既有语义一致。
"""
from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_today_internal_error_is_redacted(client, monkeypatch, caplog):
    from backend.api import today_router as module

    def _boom():
        raise RuntimeError("private today workspace detail")

    monkeypatch.setattr(module, "is_demo_mode", _boom)
    caplog.set_level(logging.ERROR, logger="backend.api.today_router")
    response = client.get("/api/today", params={"session_id": "pytest_router_session"})

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"
    assert "private today workspace detail" not in response.text
    assert "private today workspace detail" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_notes_list_internal_error_returns_500(client, monkeypatch):
    from backend.services import research_notes as notes_service

    def _boom(**_kwargs):
        raise RuntimeError("notes db exploded")

    monkeypatch.setattr(notes_service, "list_notes", _boom)
    resp = client.get(
        "/api/research-notes",
        params={"session_id": "pytest_router_session", "user_id": "default_user"},
    )
    assert resp.status_code == 500


def test_notes_create_internal_error_returns_500(client, monkeypatch):
    from backend.services import research_notes as notes_service

    def _boom(**_kwargs):
        raise RuntimeError("notes db exploded")

    monkeypatch.setattr(notes_service, "create_note", _boom)
    resp = client.post(
        "/api/research-notes",
        json={
            "session_id": "pytest_router_session",
            "user_id": "default_user",
            "title": "t",
            "content": "c",
        },
    )
    assert resp.status_code == 500


def test_notes_missing_still_404_not_500(client):
    """既有 404 语义不受影响：不存在的笔记仍返回 404。"""
    resp = client.get("/api/research-notes/note_doesnotexist99")
    assert resp.status_code == 404


def test_timeline_invalid_event_type_returns_400_not_500(client):
    """R13 回归：try 内抛出的 HTTPException(400) 不得被宽 except 重包成 500。"""
    resp = client.get(
        "/api/timeline/AAPL",
        params={"session_id": "pytest_router_session", "event_type": "bogus"},
    )
    assert resp.status_code == 400


def test_timeline_internal_error_is_redacted(client, monkeypatch, caplog):
    from backend.api import timeline_router

    def fail_get_timeline(**_kwargs):
        raise RuntimeError("private timeline database detail")

    monkeypatch.setattr(timeline_router.timeline_service, "get_timeline", fail_get_timeline)
    caplog.set_level(logging.ERROR, logger="backend.api.timeline_router")
    response = client.get(
        "/api/timeline/AAPL",
        params={"session_id": "pytest_router_session"},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"
    assert "private timeline database detail" not in response.text
    assert "private timeline database detail" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_timeline_value_error_returns_fixed_400(client, monkeypatch, caplog):
    from backend.api import timeline_router

    def fail_get_timeline(**_kwargs):
        raise ValueError("private parser path C:/secret/timeline.db")

    monkeypatch.setattr(timeline_router.timeline_service, "get_timeline", fail_get_timeline)
    caplog.set_level(logging.WARNING, logger="backend.api.timeline_router")
    response = client.get(
        "/api/timeline/AAPL",
        params={"session_id": "pytest_router_session"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid timeline request"
    assert "private parser path" not in response.text
    assert "C:/secret/timeline.db" not in response.text
    assert "private parser path" not in caplog.text
    assert "ValueError" in caplog.text


def test_portfolio_optimize_internal_error_is_redacted(client, monkeypatch):
    from backend import tools
    from backend.services import portfolio_optimizer

    secret = "private optimizer credential detail"

    monkeypatch.setattr(
        tools,
        "get_stock_historical_data",
        lambda *_args, **_kwargs: {
            "kline_data": [{"close": value} for value in range(1, 22)]
        },
    )

    def fail_optimize(**_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(portfolio_optimizer, "optimize_portfolio", fail_optimize)
    response = client.post(
        "/api/portfolio/optimize",
        json={"tickers": ["AAPL", "MSFT"], "n_simulations": 100},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"
    assert secret not in response.text


def _system_client(**overrides):
    """构造只挂载 system_router 的最小 app。

    /diagnostics/* 的依赖在 main.py 装配 SystemRouterDeps 时就绑定了函数对象，
    monkeypatch 模块属性注入不到故障，因此这里直接注入伪 deps 测路由本身。
    """
    from fastapi import FastAPI

    from backend.api.system_router import SystemRouterDeps, create_system_router

    deps_kwargs = {
        "metrics_enabled": False,
        "metrics_payload": lambda: ("", "text/plain"),
        "graph_runner_ready": lambda: True,
        "get_graph_checkpointer_info": lambda: {"backend": "memory"},
        "get_orchestrator_safe": lambda: None,
        "get_planner_ab_metrics": lambda: {},
        "get_rag_observability_store": lambda: None,
        "require_rag_read_access": lambda _request: {"role": "admin"},
        "require_rag_mutation_access": lambda _request: {"role": "admin"},
        "memory_service": None,
        "logger": logging.getLogger("backend.api.system_router"),
    }
    deps_kwargs.update(overrides)
    app = FastAPI()
    app.include_router(create_system_router(SystemRouterDeps(**deps_kwargs)))
    return TestClient(app)


def test_diagnostics_orchestrator_internal_error_is_redacted(caplog):
    """/diagnostics/orchestrator 无鉴权依赖，5xx 不得回显异常原文。"""
    secret = "private orchestrator state path C:/secret/orchestrator.state"

    class _Orchestrator:
        def get_stats(self):
            raise RuntimeError(secret)

    caplog.set_level(logging.ERROR, logger="backend.api.system_router")
    with _system_client(get_orchestrator_safe=lambda: _Orchestrator()) as client:
        response = client.get("/diagnostics/orchestrator")

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"
    assert secret not in response.text
    assert "orchestrator diagnostics failed" not in response.text
    # 服务端日志只保留异常类型，不落异常原文
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_diagnostics_orchestrator_uninitialized_keeps_existing_detail():
    """既有的固定文案不含内部细节，不应被机械替换。"""
    with _system_client(get_orchestrator_safe=lambda: None) as client:
        response = client.get("/diagnostics/orchestrator")

    assert response.status_code == 500
    assert response.json()["detail"] == "Orchestrator not initialized"


@pytest.mark.parametrize("path", ["/diagnostics/planner-ab", "/diagnostics/planner_ab"])
def test_diagnostics_planner_ab_internal_error_is_redacted(path, caplog):
    """两个别名路径都必须脱敏。"""
    secret = "private planner ab store path C:/secret/planner.db"

    def _boom():
        raise RuntimeError(secret)

    caplog.set_level(logging.ERROR, logger="backend.api.system_router")
    with _system_client(get_planner_ab_metrics=_boom) as client:
        response = client.get(path)

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"
    assert secret not in response.text
    assert "planner-ab diagnostics failed" not in response.text
    # 服务端日志只保留异常类型，不落异常原文
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def _fake_rag_service(**overrides):
    """最小 rag_service 替身，覆盖 /internal/health 读取的属性。"""
    from types import SimpleNamespace

    attrs = {
        "backend_name": "memory",
        "embedding_model": "hash",
        "vector_dim": 96,
        "count_documents": lambda: 0,
        "fallback_reason": None,
    }
    attrs.update(overrides)
    return SimpleNamespace(**attrs)


class _OkRagStore:
    def health_summary(self, **_kwargs):
        return {"enabled": True, "status": "ok", "recent_runs": [], "fallback_summary": []}


def test_internal_health_rag_observability_error_is_redacted(monkeypatch, caplog):
    """内层 except：可观测性存储故障不得回显原文，且必须把顶层置为 degraded。"""
    secret = "private rag observability store path C:/secret/rag.db"
    monkeypatch.setenv("RAG_V2_BACKEND", "auto")

    from backend.rag import hybrid_service

    monkeypatch.setattr(hybrid_service, "get_rag_service", lambda: _fake_rag_service())

    class _BoomStore:
        def health_summary(self, **_kwargs):
            raise RuntimeError(secret)

    caplog.set_level(logging.ERROR, logger="backend.api.system_router")
    with _system_client(get_rag_observability_store=lambda: _BoomStore()) as client:
        response = client.get("/internal/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    component = payload["components"]["rag_observability"]
    assert component["status"] == "error"
    assert component["error"] == "unavailable"
    assert secret not in response.text
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_internal_health_rag_service_error_is_redacted(monkeypatch, caplog):
    """外层 except：RAG 服务故障不得回显原文，顶层保持 degraded。"""
    secret = "private rag service detail C:/secret/rag-service.ini"
    monkeypatch.setenv("RAG_V2_BACKEND", "auto")

    from backend.rag import hybrid_service

    def _boom():
        raise RuntimeError(secret)

    monkeypatch.setattr(hybrid_service, "get_rag_service", _boom)

    caplog.set_level(logging.ERROR, logger="backend.api.system_router")
    with _system_client() as client:
        response = client.get("/internal/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    component = payload["components"]["rag"]
    assert component["status"] == "error"
    assert component["error"] == "unavailable"
    assert secret not in response.text
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_internal_health_fallback_reason_is_not_raw_exception(monkeypatch):
    """fallback_reason 上游即 str(exc)：保持字符串与字段名，但只暴露固定文案。"""
    secret = "private fallback detail C:/secret/pgvector.conf"
    monkeypatch.setenv("RAG_V2_BACKEND", "auto")

    from backend.rag import hybrid_service

    monkeypatch.setattr(
        hybrid_service,
        "get_rag_service",
        lambda: _fake_rag_service(fallback_reason=secret),
    )

    with _system_client(get_rag_observability_store=lambda: _OkRagStore()) as client:
        response = client.get("/internal/health")

    assert response.status_code == 200
    component = response.json()["components"]["rag"]
    assert isinstance(component["fallback_reason"], str)
    assert component["fallback_reason"] == "backend fallback active"
    assert secret not in response.text


def _market_client(**overrides):
    """构造只挂载 market_router 的最小 app（不带 security_gate 中间件）。"""
    from fastapi import FastAPI

    from backend.api.market_router import MarketRouterDeps, create_market_router

    deps_kwargs = {
        "get_orchestrator_safe": lambda: None,
        "get_stock_price": lambda _ticker: {},
        "get_company_news": lambda _ticker: {},
        "get_financial_statements": lambda _ticker: {},
        "get_financial_statements_summary": lambda _ticker: {},
        "get_stock_historical_data": lambda _ticker, **_kwargs: {},
        "detect_chart_type": lambda _query, _ticker: {},
        "logger": logging.getLogger("backend.api.market_router"),
    }
    deps_kwargs.update(overrides)
    app = FastAPI()
    app.include_router(create_market_router(MarketRouterDeps(**deps_kwargs)))
    return TestClient(app)


def test_market_historical_internal_error_is_redacted(monkeypatch, caplog, capsys):
    """/api/market/historical 的 500 不得回显异常原文。"""
    secret = "private baostock cache path C:/secret/historical.sqlite"

    from backend.services import historical_data_store

    def _boom(**_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(historical_data_store, "fetch_and_cache_kline", _boom)
    caplog.set_level(logging.ERROR, logger="backend.api.market_router")
    with _market_client() as client:
        response = client.get("/api/market/historical/AAPL")

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"
    assert secret not in response.text
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text
    captured = capsys.readouterr()
    assert secret not in captured.out
    assert secret not in captured.err


def _patch_pdf(monkeypatch, service_factory):
    """放行套餐校验并替换 PDF 服务工厂（两者均在函数内 import）。"""
    from backend.services import entitlements, pdf_export

    monkeypatch.setattr(entitlements, "enforce_feature", lambda *_a, **_kw: None)
    monkeypatch.setattr(pdf_export, "get_pdf_service", service_factory)


def test_export_pdf_internal_error_is_redacted(monkeypatch, caplog, capsys):
    """/api/export/pdf 的 500 不得回显异常原文，且不得再打 traceback 到 stdout/stderr。"""
    secret = "private pdf template path C:/secret/report-template.html"

    class _Service:
        def export_conversation(self, *_a, **_kw):
            raise RuntimeError(secret)

    _patch_pdf(monkeypatch, lambda: _Service())
    caplog.set_level(logging.ERROR, logger="backend.api.market_router")
    with _market_client() as client:
        response = client.post(
            "/api/export/pdf", json={"messages": [{"role": "user", "content": "hi"}]}
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"
    assert secret not in response.text
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text
    captured = capsys.readouterr()
    assert secret not in captured.out
    assert secret not in captured.err
    assert "Traceback" not in captured.err


def test_export_pdf_import_error_returns_fixed_503(monkeypatch, caplog):
    """ImportError 仍是 503，但文案固定，不暴露缺失依赖细节。"""
    secret = "No module named 'private_pdf_backend'"

    def _boom():
        raise ImportError(secret)

    _patch_pdf(monkeypatch, _boom)
    caplog.set_level(logging.ERROR, logger="backend.api.market_router")
    with _market_client() as client:
        response = client.post(
            "/api/export/pdf", json={"messages": [{"role": "user", "content": "hi"}]}
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "PDF export unavailable"
    assert secret not in response.text
    assert secret not in caplog.text
    assert "ImportError" in caplog.text


def test_export_pdf_internal_error_survives_missing_logger(monkeypatch, capsys):
    """回归：logger=None 时记日志不得抛异常，否则固定 JSON 500 会退化成框架默认响应。"""
    secret = "private pdf template path C:/secret/report-template.html"

    class _Service:
        def export_conversation(self, *_a, **_kw):
            raise RuntimeError(secret)

    _patch_pdf(monkeypatch, lambda: _Service())
    with _market_client(logger=None) as client:
        response = client.post(
            "/api/export/pdf", json={"messages": [{"role": "user", "content": "hi"}]}
        )

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["detail"] == "Internal server error"
    assert secret not in response.text
    captured = capsys.readouterr()
    assert secret not in captured.out
    assert secret not in captured.err


def test_export_pdf_import_error_survives_missing_logger(monkeypatch, capsys):
    """回归：logger=None 时 ImportError 仍须是 503 JSON，不得退化成 500。"""
    secret = "No module named 'private_pdf_backend'"

    def _boom():
        raise ImportError(secret)

    _patch_pdf(monkeypatch, _boom)
    with _market_client(logger=None) as client:
        response = client.post(
            "/api/export/pdf", json={"messages": [{"role": "user", "content": "hi"}]}
        )

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["detail"] == "PDF export unavailable"
    assert secret not in response.text
    captured = capsys.readouterr()
    assert secret not in captured.out
    assert secret not in captured.err


def test_export_pdf_error_survives_logger_without_error_method(monkeypatch):
    """回归：logger 不含可调用 error 时也不得覆盖原始异常处理。"""
    secret = "private pdf detail C:/secret/font.ttf"

    class _Service:
        def export_conversation(self, *_a, **_kw):
            raise RuntimeError(secret)

    _patch_pdf(monkeypatch, lambda: _Service())
    with _market_client(logger=object()) as client:
        response = client.post(
            "/api/export/pdf", json={"messages": [{"role": "user", "content": "hi"}]}
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"
    assert secret not in response.text


def test_export_pdf_entitlement_403_is_preserved(monkeypatch):
    """守护：套餐 403 的结构化 detail 必须原样透出，不被宽 except 重包成 500。"""
    from fastapi import HTTPException as _HTTPException

    from backend.services import entitlements

    def _deny(*_a, **_kw):
        raise _HTTPException(
            status_code=403,
            detail={"code": "plan_feature_required", "feature": "export_pdf"},
        )

    monkeypatch.setattr(entitlements, "enforce_feature", _deny)
    with _market_client() as client:
        response = client.post(
            "/api/export/pdf", json={"messages": [{"role": "user", "content": "hi"}]}
        )

    assert response.status_code == 403
    detail = response.json()["detail"]
    assert detail["code"] == "plan_feature_required"
    assert detail["feature"] == "export_pdf"


def test_export_pdf_empty_messages_still_400(monkeypatch):
    """守护：既有 400 业务文案不受影响。"""
    _patch_pdf(monkeypatch, lambda: object())
    with _market_client() as client:
        response = client.post("/api/export/pdf", json={"messages": []})

    assert response.status_code == 400
    assert response.json()["detail"] == "messages 不能为空"


def test_internal_health_error_handling_survives_missing_logger(monkeypatch):
    """现有夹具传 logger=None：错误处理本身不得再抛异常。"""
    monkeypatch.setenv("RAG_V2_BACKEND", "auto")

    from backend.rag import hybrid_service

    def _boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(hybrid_service, "get_rag_service", _boom)

    with _system_client(logger=None) as client:
        response = client.get("/internal/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["components"]["rag"]["error"] == "unavailable"
