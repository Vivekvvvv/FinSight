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


@pytest.mark.parametrize("parameter", ["from", "to"])
def test_timeline_rejects_invalid_date_filter_before_service(client, monkeypatch, parameter):
    from backend.api import timeline_router

    calls = []

    def _get_timeline(**kwargs):
        calls.append(kwargs)
        return []

    monkeypatch.setattr(timeline_router.timeline_service, "get_timeline", _get_timeline)
    response = client.get(
        "/api/timeline/AAPL",
        params={"session_id": "test-session", parameter: "not-an-iso-date"},
    )

    assert response.status_code == 422
    assert calls == []


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


def test_rag_db_browser_value_error_is_redacted():
    secret = "PRIVATE C:/secret/rag-observability.db"

    class _Store:
        def browse_db_table(self, **_kwargs):
            raise ValueError(secret)

    with _system_client(get_rag_observability_store=lambda: _Store()) as client:
        response = client.get("/diagnostics/rag/db-browser/runs")

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid RAG diagnostics request"
    assert secret not in response.text


def test_rag_search_preview_value_error_is_redacted():
    secret = "PRIVATE C:/secret/rag-search-index.json"

    class _Store:
        def search_preview(self, **_kwargs):
            raise ValueError(secret)

    with _system_client(get_rag_observability_store=lambda: _Store()) as client:
        response = client.post(
            "/diagnostics/rag/search-preview",
            json={"query": "AAPL", "collection": "reports"},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid RAG diagnostics request"
    assert secret not in response.text


def test_research_note_image_value_error_is_redacted(client, monkeypatch):
    from backend.api import research_notes_router

    secret = "PRIVATE C:/secret/note-image-cache"

    async def _fail_save_image(**_kwargs):
        raise ValueError(secret)

    monkeypatch.setattr(
        research_notes_router.research_notes,
        "get_note",
        lambda _note_id: {"user_id": "default_user"},
    )
    monkeypatch.setattr(research_notes_router.note_images, "save_image", _fail_save_image)

    response = client.post(
        "/api/research-notes/note-1/images",
        files={"file": ("chart.png", b"image", "image/png")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid image upload"
    assert secret not in response.text


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


class _FailingLogger:
    def warning(self, *_args, **_kwargs):
        raise RuntimeError("logger unavailable")

    def error(self, *_args, **_kwargs):
        raise RuntimeError("logger unavailable")

    def info(self, *_args, **_kwargs):
        raise RuntimeError("logger unavailable")


def _broken_logger(mode: str):
    if mode == "none":
        return None
    if mode == "missing_method":
        return object()
    if mode == "raises":
        return _FailingLogger()
    raise AssertionError(f"Unexpected logger mode: {mode}")


def _config_client(**overrides):
    from fastapi import FastAPI

    from backend.api.config_router import ConfigRouterDeps, create_config_router
    from backend.security.auth import Principal, require_admin_principal

    deps_kwargs = {
        "project_root": ".",
        "logger": logging.getLogger("backend.api.config_router"),
    }
    deps_kwargs.update(overrides)
    app = FastAPI()
    app.dependency_overrides[require_admin_principal] = lambda: Principal(
        user_id="test-admin",
        role="admin",
        auth_type="test",
    )
    app.include_router(create_config_router(ConfigRouterDeps(**deps_kwargs)))
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


def test_export_pdf_rejects_oversized_message_list(monkeypatch):
    class _Service:
        def export_conversation(self, *_args, **_kwargs):
            raise AssertionError("oversized payload must be rejected before rendering")

    _patch_pdf(monkeypatch, lambda: _Service())
    with _market_client() as client:
        response = client.post(
            "/api/export/pdf",
            json={"messages": [{"role": "user", "content": "x"}] * 501},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Too many messages"


def test_export_pdf_rejects_oversized_chart_list(monkeypatch):
    class _Service:
        def export_with_charts(self, *_args, **_kwargs):
            raise AssertionError("oversized payload must be rejected before rendering")

    _patch_pdf(monkeypatch, lambda: _Service())
    with _market_client() as client:
        response = client.post(
            "/api/export/pdf",
            json={
                "messages": [{"role": "user", "content": "x"}],
                "charts": [{"ticker": "AAPL"}] * 101,
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Too many charts"


def test_export_pdf_rejects_oversized_payload_before_rendering(monkeypatch):
    class _Service:
        def export_conversation(self, *_args, **_kwargs):
            raise AssertionError("oversized payload must be rejected before rendering")

    _patch_pdf(monkeypatch, lambda: _Service())
    with _market_client() as client:
        response = client.post(
            "/api/export/pdf",
            json={"messages": [{"role": "user", "content": "x" * (1024 * 1024)}]},
        )

    assert response.status_code == 413
    assert response.json()["detail"] == "PDF export payload is too large"


def test_export_pdf_drops_client_supplied_local_image_path(monkeypatch):
    captured = {}

    class _Service:
        def export_with_charts(self, messages, charts, **kwargs):
            captured["messages"] = messages
            captured["charts"] = charts
            captured.update(kwargs)
            return b"%PDF-1.4 test"

    _patch_pdf(monkeypatch, lambda: _Service())
    with _market_client() as client:
        response = client.post(
            "/api/export/pdf",
            json={
                "messages": [{"role": "user", "content": "hi"}],
                "charts": [
                    {
                        "ticker": "AAPL",
                        "chart_type": "line",
                        "image_path": "C:/private/server-chart.png",
                    }
                ],
            },
        )

    assert response.status_code == 200
    assert captured["charts"] == [{"ticker": "AAPL", "chart_type": "line"}]


@pytest.mark.parametrize("path", ["/api/stock/kline/AAPL", "/api/kline/AAPL"])
def test_kline_internal_error_returns_fixed_502(path, monkeypatch, caplog):
    """M2：kline 异常（demo 兜底不可用时）不得再压成 200+str(exc)，改固定 502。"""
    secret = "private kline provider path C:/secret/kline-cache.db"
    monkeypatch.delenv("FINSIGHT_DEMO_MODE", raising=False)

    def _boom(_ticker, **_kwargs):
        raise RuntimeError(secret)

    caplog.set_level(logging.WARNING, logger="backend.api.market_router")
    with _market_client(get_stock_historical_data=_boom) as client:
        response = client.get(path)

    assert response.status_code == 502
    assert response.json()["detail"] == "Kline data unavailable"
    assert secret not in response.text
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_kline_demo_fallback_preserved_on_exception(monkeypatch):
    """守护：demo 模式下异常仍先走 demo 兜底，保持 200。"""
    monkeypatch.setenv("FINSIGHT_DEMO_MODE", "true")

    def _boom(_ticker, **_kwargs):
        raise RuntimeError("boom")

    with _market_client(get_stock_historical_data=_boom) as client:
        response = client.get("/api/kline/AAPL")

    assert response.status_code == 200
    assert response.json()["data"]["source"] == "demo"


def test_kline_upstream_error_payload_passthrough_preserved(monkeypatch):
    """守护：上游正常返回的固定 error 文案仍按 200 透传（非异常路径）。"""
    monkeypatch.delenv("FINSIGHT_DEMO_MODE", raising=False)

    with _market_client(
        get_stock_historical_data=lambda _t, **_kw: {"error": "history unavailable"}
    ) as client:
        response = client.get("/api/kline/AAPL")

    assert response.status_code == 200
    assert response.json()["data"]["error"] == "history unavailable"


def test_intraday_internal_error_returns_fixed_502(monkeypatch, caplog):
    """M2：intraday 异常改固定 502，不回显异常原文。"""
    secret = "private intraday provider path C:/secret/tencent.ini"

    from backend.api import market_router as market_module

    monkeypatch.setattr(market_module, "is_cn_symbol", lambda _t: True)

    def _boom(_ticker):
        raise RuntimeError(secret)

    monkeypatch.setattr(market_module, "fetch_cn_intraday", _boom)
    caplog.set_level(logging.WARNING, logger="backend.api.market_router")
    with _market_client() as client:
        response = client.get("/api/stock/intraday/600519.SS")

    assert response.status_code == 502
    assert response.json()["detail"] == "Intraday data unavailable"
    assert secret not in response.text
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_intraday_non_cn_business_message_preserved():
    """守护：非A股的既有 200 固定业务文案不受影响。"""
    with _market_client() as client:
        response = client.get("/api/stock/intraday/AAPL")

    assert response.status_code == 200
    assert response.json()["data"]["error"] == "intraday data not available"


def test_chart_detect_internal_error_reason_is_fixed(monkeypatch, caplog):
    """M2：chart/detect 保持 200，reason 改固定 detector_error，日志 type-only。"""
    secret = "private detector model path C:/secret/detector.bin"

    def _boom(_query, _ticker):
        raise RuntimeError(secret)

    caplog.set_level(logging.WARNING, logger="backend.api.market_router")
    with _market_client(detect_chart_type=_boom) as client:
        response = client.post(
            "/api/chart/detect", json={"query": "chart AAPL trend", "ticker": "AAPL"}
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["reason"] == "detector_error"
    assert "AAPL" in payload["ticker_candidates"]
    assert secret not in response.text
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_chart_detect_empty_query_reason_preserved():
    """守护：empty_query 的既有 reason 枚举不受影响。"""
    with _market_client() as client:
        response = client.post("/api/chart/detect", json={"query": "", "ticker": "AAPL"})

    assert response.status_code == 200
    assert response.json()["reason"] == "empty_query"


def test_market_warning_helper_survives_missing_logger(monkeypatch):
    """回归：logger=None 时新 warning helper 不得改变 502 / 200 响应契约。"""
    monkeypatch.delenv("FINSIGHT_DEMO_MODE", raising=False)

    def _boom_kline(_ticker, **_kwargs):
        raise RuntimeError("boom")

    with _market_client(get_stock_historical_data=_boom_kline, logger=None) as client:
        kline_resp = client.get("/api/kline/AAPL")

    assert kline_resp.status_code == 502
    assert kline_resp.headers["content-type"].startswith("application/json")
    assert kline_resp.json()["detail"] == "Kline data unavailable"

    def _boom_detect(_query, _ticker):
        raise RuntimeError("boom")

    with _market_client(detect_chart_type=_boom_detect, logger=None) as client:
        chart_resp = client.post(
            "/api/chart/detect", json={"query": "chart AAPL trend", "ticker": "AAPL"}
        )

    assert chart_resp.status_code == 200
    assert chart_resp.json()["reason"] == "detector_error"


@pytest.mark.parametrize("logger_mode", ["none", "missing_method", "raises"])
def test_internal_health_error_handling_survives_broken_logger(monkeypatch, logger_mode):
    """日志器不可用时，internal-health 的既有降级响应不得退化。"""
    monkeypatch.setenv("RAG_V2_BACKEND", "auto")

    from backend.rag import hybrid_service

    def _boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(hybrid_service, "get_rag_service", _boom)

    with _system_client(logger=_broken_logger(logger_mode)) as client:
        response = client.get("/internal/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["components"]["rag"]["error"] == "unavailable"


@pytest.mark.parametrize("logger_mode", ["none", "missing_method", "raises"])
@pytest.mark.parametrize(
    ("route", "failure_point", "expected_status", "expected_detail"),
    [
        ("/api/stock/price/AAPL", "price", 502, "无法获取 AAPL 价格数据"),
        ("/api/stock/news/AAPL", "news", 502, "无法获取 AAPL 新闻数据"),
        ("/api/financials/AAPL", "financials", 502, "无法获取 AAPL 财务数据"),
        ("/api/financials/AAPL/summary", "financials_summary", 502, "无法获取 AAPL 财务摘要"),
        ("/api/market/historical/AAPL", "historical", 500, "Internal server error"),
    ],
)
def test_market_error_paths_survive_broken_loggers(
    monkeypatch,
    logger_mode,
    route,
    failure_point,
    expected_status,
    expected_detail,
):
    """五个既有错误出口不得因日志器故障退化为框架默认响应。"""
    secret = "private market provider detail C:/secret/market-provider.ini"
    monkeypatch.delenv("FINSIGHT_DEMO_MODE", raising=False)

    def _boom(*_args, **_kwargs):
        raise RuntimeError(secret)

    overrides = {}
    if failure_point == "price":
        from backend.api import market_router as market_module

        monkeypatch.setattr(market_module, "resolve_live_quote", _boom)
    elif failure_point == "historical":
        from backend.services import historical_data_store

        monkeypatch.setattr(historical_data_store, "fetch_and_cache_kline", _boom)
    else:
        dependency_name = {
            "news": "get_company_news",
            "financials": "get_financial_statements",
            "financials_summary": "get_financial_statements_summary",
        }[failure_point]
        overrides[dependency_name] = _boom

    with _market_client(logger=_broken_logger(logger_mode), **overrides) as client:
        response = client.get(route)

    assert response.status_code == expected_status
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["detail"] == expected_detail
    assert secret not in response.text


@pytest.mark.parametrize("logger_mode", ["none", "missing_method", "raises"])
@pytest.mark.parametrize(
    "route",
    [
        "/diagnostics/orchestrator",
        "/diagnostics/planner-ab",
        "/diagnostics/planner_ab",
    ],
)
def test_diagnostics_error_paths_survive_broken_loggers(logger_mode, route):
    """两条 diagnostics 错误路径经安全日志器后仍返回既有 JSON 500。"""
    secret = "private diagnostics state C:/secret/diagnostics.state"

    def _boom():
        raise RuntimeError(secret)

    if route == "/diagnostics/orchestrator":
        class _Orchestrator:
            def get_stats(self):
                _boom()

        overrides = {"get_orchestrator_safe": lambda: _Orchestrator()}
    else:
        overrides = {"get_planner_ab_metrics": _boom}

    with _system_client(logger=_broken_logger(logger_mode), **overrides) as client:
        response = client.get(route)

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["detail"] == "Internal server error"
    assert secret not in response.text


@pytest.mark.parametrize("logger_mode", ["none", "missing_method", "raises"])
def test_config_save_survives_broken_logger(monkeypatch, tmp_path, logger_mode):
    """配置保存成功不能因可选日志器不可用而降级为错误响应。"""
    import json

    from backend.api import config_router as config_module

    config_path = tmp_path / f"config-{logger_mode}.json"
    monkeypatch.setattr(config_module, "USER_CONFIG_PATH", str(config_path))

    with _config_client(logger=_broken_logger(logger_mode)) as client:
        response = client.post("/api/config", json={"layout_mode": "wide"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["success"] is True
    assert config_path.is_file()
    assert json.loads(config_path.read_text(encoding="utf-8"))["layout_mode"] == "wide"


def test_config_get_internal_error_is_redacted(monkeypatch, caplog, capsys):
    secret = "private config path C:/secret/user_config.json"

    from backend.api import config_router as config_module

    def _boom(*_args, **_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(config_module, "open", _boom, raising=False)
    caplog.set_level(logging.ERROR, logger="backend.api.config_router")
    with _config_client() as client:
        response = client.get("/api/config")

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"success": False, "error": "Internal server error"}
    assert secret not in response.text
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text
    captured = capsys.readouterr()
    assert secret not in captured.out
    assert secret not in captured.err


def test_config_save_internal_error_is_redacted(monkeypatch, tmp_path, caplog, capsys):
    secret = "private config temp file C:/secret/config.tmp"

    from backend.api import config_router as config_module

    def _boom(*_args, **_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(config_module, "USER_CONFIG_PATH", str(tmp_path / "user_config.json"))
    monkeypatch.setattr(config_module.tempfile, "mkstemp", _boom)
    caplog.set_level(logging.ERROR, logger="backend.api.config_router")
    with _config_client() as client:
        response = client.post("/api/config", json={"layout_mode": "wide"})

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["success"] is False
    assert response.json()["error"] == "Internal server error"
    assert secret not in response.text
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text
    captured = capsys.readouterr()
    assert secret not in captured.out
    assert secret not in captured.err
    assert "Traceback" not in captured.err


def test_personas_internal_error_is_redacted(monkeypatch, caplog, capsys):
    secret = "private personas registry C:/secret/personas.yaml"

    from backend import personas

    def _boom(*_args, **_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(personas, "list_personas", _boom)
    caplog.set_level(logging.ERROR, logger="backend.api.config_router")
    with _config_client() as client:
        response = client.get("/api/personas")

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {
        "success": False,
        "error": "Internal server error",
        "personas": [],
    }
    assert secret not in response.text
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text
    captured = capsys.readouterr()
    assert secret not in captured.out
    assert secret not in captured.err
    assert "Traceback" not in captured.err


@pytest.mark.parametrize("logger_mode", ["none", "missing_method", "raises"])
@pytest.mark.parametrize("failure_point", ["get_config", "save_config", "personas"])
def test_config_error_paths_survive_broken_loggers(
    monkeypatch,
    tmp_path,
    logger_mode,
    failure_point,
):
    secret = "private config dependency C:/secret/config-dependency.ini"

    from backend.api import config_router as config_module

    def _boom(*_args, **_kwargs):
        raise RuntimeError(secret)

    if failure_point == "get_config":
        monkeypatch.setattr(config_module, "open", _boom, raising=False)
        method = "get"
        path = "/api/config"
        payload = None
    elif failure_point == "save_config":
        monkeypatch.setattr(config_module, "USER_CONFIG_PATH", str(tmp_path / "user_config.json"))
        monkeypatch.setattr(config_module.tempfile, "mkstemp", _boom)
        method = "post"
        path = "/api/config"
        payload = {"layout_mode": "wide"}
    else:
        from backend import personas

        monkeypatch.setattr(personas, "list_personas", _boom)
        method = "get"
        path = "/api/personas"
        payload = None

    with _config_client(logger=_broken_logger(logger_mode)) as client:
        response = getattr(client, method)(path, json=payload) if payload else getattr(client, method)(path)

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["success"] is False
    assert response.json()["error"] == "Internal server error"
    assert secret not in response.text


def test_config_get_redacts_persisted_secrets(monkeypatch, tmp_path):
    import json

    from backend.api import config_router as config_module

    secret = "private-config-secret"
    config_path = tmp_path / "user_config.json"
    config_path.write_text(json.dumps({"llm_api_key": secret, "layout_mode": "wide"}), encoding="utf-8")
    monkeypatch.setattr(config_module, "USER_CONFIG_PATH", str(config_path))

    with _config_client() as client:
        response = client.get("/api/config")

    assert response.status_code == 200
    assert response.json()["config"]["llm_api_key"] == "*" * len(secret)
    assert secret not in response.text


def _agent_client(memory_service):
    from fastapi import FastAPI

    from backend.api.agent_router import AgentRouterDeps, create_agent_router
    from backend.security.auth import Principal, get_current_user

    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: Principal(
        user_id="test-user",
        role="user",
        auth_type="test",
    )
    app.include_router(create_agent_router(AgentRouterDeps(memory_service=memory_service)))
    return TestClient(app)


def _risk_lens_client():
    from fastapi import FastAPI

    from backend.api.risk_lens_router import RiskLensRouterDeps, create_risk_lens_router
    from backend.security.auth import Principal, get_current_user

    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: Principal(
        user_id="test-user",
        role="user",
        auth_type="test",
    )
    app.include_router(create_risk_lens_router(RiskLensRouterDeps(resolve_thread_id=lambda value: value or "")))
    return TestClient(app)


def test_agent_preferences_get_internal_error_is_redacted(caplog, capsys):
    secret = "private agent preferences C:/secret/agent-preferences.json"

    class _MemoryService:
        def get_user_profile(self, _user_id):
            raise RuntimeError(secret)

    caplog.set_level(logging.ERROR, logger="backend.api.agent_router")
    with _agent_client(_MemoryService()) as client:
        response = client.get("/api/agents/preferences")

    assert response.status_code == 500
    assert response.json() == {"success": False, "error": "Internal server error"}
    assert secret not in response.text
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text
    captured = capsys.readouterr()
    assert secret not in captured.out
    assert secret not in captured.err


def test_agent_preferences_update_internal_error_is_redacted(caplog, capsys):
    secret = "private agent preferences C:/secret/agent-preferences.json"

    class _Profile:
        preferences = {}

    class _MemoryService:
        def get_user_profile(self, _user_id):
            return _Profile()

        def update_user_profile(self, _profile):
            raise RuntimeError(secret)

    caplog.set_level(logging.ERROR, logger="backend.api.agent_router")
    with _agent_client(_MemoryService()) as client:
        response = client.put(
            "/api/agents/preferences",
            json={"preferences": {"maxRounds": 4}},
        )

    assert response.status_code == 500
    assert response.json() == {"success": False, "error": "Internal server error"}
    assert secret not in response.text
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text
    captured = capsys.readouterr()
    assert secret not in captured.out
    assert secret not in captured.err


@pytest.mark.parametrize("method", ["get", "put"])
def test_agent_preferences_missing_memory_service_returns_503(method):
    with _agent_client(None) as client:
        response = getattr(client, method)(
            "/api/agents/preferences",
            **({"json": {"preferences": {}}} if method == "put" else {}),
        )

    assert response.status_code == 503
    assert response.json() == {
        "success": False,
        "error": "MemoryService not initialized",
    }


def test_risk_lens_internal_error_is_redacted(monkeypatch, caplog, capsys):
    secret = "private portfolio store C:/secret/portfolio-store.json"

    from backend.services import portfolio_store

    def _boom(*_args, **_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(portfolio_store, "get_positions", _boom)
    caplog.set_level(logging.ERROR, logger="backend.api.risk_lens_router")
    with _risk_lens_client() as client:
        response = client.get(
            "/api/portfolio/risk-lens",
            params={"session_id": "private:test-user:default"},
        )

    payload = response.json()
    assert response.status_code == 500
    assert payload["success"] is False
    assert payload["error"] == "Internal server error"
    assert payload["risk_score"] == 0
    assert payload["concentration_risk"] == []
    assert payload["next_actions"] == []
    assert secret not in response.text
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text
    captured = capsys.readouterr()
    assert secret not in captured.out
    assert secret not in captured.err


def test_risk_lens_history_internal_error_is_redacted(monkeypatch, caplog, capsys):
    secret = "private risk history C:/secret/risk-snapshots.sqlite"

    from backend.api import risk_lens_router as risk_lens_module

    def _boom(*_args, **_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(risk_lens_module, "get_risk_snapshots_history", _boom)
    caplog.set_level(logging.ERROR, logger="backend.api.risk_lens_router")
    with _risk_lens_client() as client:
        response = client.get(
            "/api/portfolio/risk-lens/history",
            params={"session_id": "private:test-user:default"},
        )

    assert response.status_code == 500
    assert response.json() == {
        "success": False,
        "error": "Internal server error",
        "snapshots": [],
    }
    assert secret not in response.text
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text
    captured = capsys.readouterr()
    assert secret not in captured.out
    assert secret not in captured.err


def _user_client(memory_service, user_profile_cls):
    from fastapi import FastAPI

    from backend.api.user_router import UserRouterDeps, create_user_router
    from backend.security.auth import Principal, get_current_user

    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: Principal(
        user_id="test-user",
        role="user",
        auth_type="test",
    )
    app.include_router(
        create_user_router(
            UserRouterDeps(
                memory_service=memory_service,
                user_profile_cls=user_profile_cls,
            )
        )
    )
    return TestClient(app)


@pytest.mark.parametrize(
    ("method", "path", "request_kwargs"),
    [
        ("GET", "/api/user/profile", {}),
        ("POST", "/api/user/profile", {"json": {"profile": {"risk_tolerance": "medium"}}}),
        ("POST", "/api/user/watchlist/add", {"json": {"ticker": "AAPL"}}),
        ("POST", "/api/user/watchlist/update", {"json": {"ticker": "AAPL"}}),
        ("GET", "/api/user/watchlist", {}),
        ("POST", "/api/user/watchlist/remove", {"json": {"ticker": "AAPL"}}),
    ],
    ids=["profile_get", "profile_save", "watchlist_add", "watchlist_update", "watchlist_list", "watchlist_remove"],
)
def test_user_router_internal_errors_are_redacted(method, path, request_kwargs, caplog, capsys):
    secret = "private user memory C:/secret/user-memory.json"

    def _boom(*_args, **_kwargs):
        raise RuntimeError(secret)

    class _MemoryService:
        def get_user_profile(self, _user_id):
            _boom()

        def update_user_profile(self, _profile):
            _boom()

        def add_to_watchlist(self, *_args, **_kwargs):
            _boom()

        def update_watchlist_meta(self, *_args, **_kwargs):
            _boom()

        def list_watchlist_items(self, _user_id):
            _boom()

        def remove_from_watchlist(self, *_args, **_kwargs):
            _boom()

    class _UserProfile:
        @classmethod
        def from_dict(cls, _data):
            _boom()

    caplog.set_level(logging.ERROR, logger="backend.api.user_router")
    with _user_client(_MemoryService(), _UserProfile) as client:
        response = client.request(method, path, **request_kwargs)

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"success": False, "error": "Internal server error"}
    assert secret not in response.text
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text
    captured = capsys.readouterr()
    assert secret not in captured.out
    assert secret not in captured.err


@pytest.mark.parametrize(
    ("method", "path", "request_kwargs"),
    [
        ("GET", "/api/user/profile", {}),
        ("POST", "/api/user/profile", {"json": {"profile": {}}}),
        ("POST", "/api/user/watchlist/add", {"json": {"ticker": "AAPL"}}),
        ("POST", "/api/user/watchlist/update", {"json": {"ticker": "AAPL"}}),
        ("GET", "/api/user/watchlist", {}),
        ("POST", "/api/user/watchlist/remove", {"json": {"ticker": "AAPL"}}),
    ],
)
def test_user_router_missing_memory_service_returns_503(method, path, request_kwargs):
    with _user_client(None, object) as client:
        response = client.request(method, path, **request_kwargs)

    assert response.status_code == 503
    assert response.json() == {"error": "MemoryService not initialized"}


@pytest.mark.parametrize(
    ("path", "payload", "expected_error"),
    [
        ("/api/user/watchlist/add", {}, "Ticker is required"),
        ("/api/user/watchlist/add", {"ticker": "AAPL", "tags": "bad"}, "tags must be a list"),
        ("/api/user/watchlist/update", {}, "Ticker is required"),
        ("/api/user/watchlist/update", {"ticker": "AAPL", "tags": "bad"}, "tags must be a list"),
        ("/api/user/watchlist/add", {"ticker": "A" * 33}, "Invalid ticker"),
        ("/api/user/watchlist/add", {"ticker": "AAPL", "tags": ["tag"] * 21}, "Invalid tags"),
        ("/api/user/watchlist/update", {"ticker": "AAPL", "note": "x" * 2001}, "Invalid note"),
        ("/api/user/watchlist/update", {"ticker": "AAPL", "priority": 6}, "Invalid priority"),
        ("/api/user/watchlist/remove", {}, "Ticker is required"),
    ],
)
def test_user_router_invalid_watchlist_request_returns_400(path, payload, expected_error):
    class _MemoryService:
        pass

    with _user_client(_MemoryService(), object) as client:
        response = client.post(path, json=payload)

    assert response.status_code == 400
    assert response.json() == {"success": False, "error": expected_error}


def test_user_router_rejects_oversized_profile_and_watchlist_search():
    class _MemoryService:
        def list_watchlist_items(self, _user_id):
            return []

    class _UserProfile:
        @classmethod
        def from_dict(cls, _data):
            raise AssertionError("oversized profile must not be constructed")

    with _user_client(_MemoryService(), _UserProfile) as client:
        profile_response = client.post(
            "/api/user/profile",
            json={"profile": {"preferences": {"blob": "x" * (256 * 1024)}}},
        )
        search_response = client.get("/api/user/watchlist", params={"q": "x" * 129})

    assert profile_response.status_code == 413
    assert profile_response.json()["error"] == "profile is too large"
    assert search_response.status_code == 422


@pytest.mark.parametrize(
    ("content", "expected_error"),
    [
        ('{"profile":{"preferences":{"score":NaN}}}', "Invalid profile payload"),
        ('{"profile":{"preferences":[]}}', "preferences must be an object"),
        ('{"profile":{"watchlist_meta":[]}}', "watchlist_meta must be an object"),
    ],
)
def test_user_router_rejects_invalid_profile_payload(content, expected_error):
    class _MemoryService:
        def update_user_profile(self, _profile):
            raise AssertionError("invalid profile must not be persisted")

    with _user_client(_MemoryService(), object) as client:
        response = client.post(
            "/api/user/profile",
            content=content,
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 400
    assert response.json() == {"success": False, "error": expected_error}


@pytest.mark.parametrize(
    "path",
    [
        "/diagnostics/orchestrator",
        "/diagnostics/planner-ab",
        "/diagnostics/planner_ab",
    ],
)
def test_diagnostics_require_rag_read_access(path):
    from fastapi import HTTPException

    calls = []

    def _deny(request):
        calls.append(request.url.path)
        raise HTTPException(status_code=401, detail="Authentication required")

    with _system_client(
        get_orchestrator_safe=lambda: (_ for _ in ()).throw(AssertionError("business dependency called")),
        get_planner_ab_metrics=lambda: (_ for _ in ()).throw(AssertionError("business dependency called")),
        require_rag_read_access=_deny,
    ) as client:
        response = client.get(path)

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"
    assert calls == [path]
