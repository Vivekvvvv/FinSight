"""新执行请求必须按实际报告模式校验认证用户的套餐。"""

import asyncio
import importlib
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.chat_router import ChatRouterDeps, create_chat_router
from backend.api.execution_router import ExecutionRouterDeps, create_execution_router
from backend.api.session_context import _build_ui_context, _resolve_thread_id
from backend.security.auth import Principal, get_current_user


ENDPOINTS = ("/chat/supervisor", "/chat/supervisor/stream", "/api/execute")


@pytest.fixture
def report_harness(tmp_path, monkeypatch):
    from backend.api import execution_router
    from backend.services import entitlements, execution_service

    monkeypatch.setenv("DEV_MODE", "0")
    monkeypatch.setattr(entitlements, "PLANS_FILE", tmp_path / "plans.json")
    plans = entitlements.EntitlementsService()
    monkeypatch.setattr(entitlements, "_service_instance", plans)
    principal = {"value": Principal("alice", "alice@example.invalid", auth_type="api_key")}
    calls = []
    reference = {"query": None}

    async def get_runner():
        return object()

    async def run_graph(_runner, **kwargs):
        calls.append(kwargs)
        return {"artifacts": {"draft_markdown": "完成"}}

    async def pipeline(**kwargs):
        calls.append(kwargs)
        yield {"type": "done"}

    monkeypatch.setattr(importlib.import_module("backend.graph.runner"), "run_graph_traced", run_graph)
    monkeypatch.setattr(importlib.import_module("backend.graph.report_builder"), "build_report_payload", lambda **_kwargs: None)
    monkeypatch.setattr(execution_service, "run_graph_pipeline", pipeline)
    monkeypatch.setattr(execution_router, "run_graph_pipeline", pipeline)
    shared_deps = {
        "get_graph_runner": get_runner,
        "resolve_thread_id": _resolve_thread_id,
        "schedule_report_index": lambda **_kwargs: None,
        "update_session_context": lambda **_kwargs: None,
        "redact_sensitive_payload": lambda payload: payload,
        "is_raw_trace_event": lambda _event: False,
        "contract_info": lambda: {},
        "sse_event_schema_version": "chat.sse.v1",
    }
    app = FastAPI()
    app.include_router(create_chat_router(ChatRouterDeps(
        **shared_deps,
        build_ui_context=_build_ui_context,
        resolve_query_reference=lambda query, _thread: reference["query"] or query,
        resolve_trace_raw_enabled=lambda _request: False,
        get_session_context=lambda _thread: None,
        chat_history_store=None,
        chat_response_schema_version="chat.response.v1",
    )))
    app.include_router(create_execution_router(ExecutionRouterDeps(**shared_deps)))
    app.dependency_overrides[get_current_user] = lambda: principal["value"]
    return SimpleNamespace(client=TestClient(app), plans=plans, principal=principal, calls=calls, reference=reference)


def _request(endpoint, query, output_mode=None):
    payload = {"query": query}
    if output_mode is not None:
        if endpoint == "/api/execute":
            payload["output_mode"] = output_mode
        else:
            payload["options"] = {"output_mode": output_mode}
    return payload


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("query,output_mode", [
    ("分析 AAPL", "investment_report"),
    ("生成 AAPL 投资报告", None),
])
def test_free_user_cannot_execute_explicit_or_inferred_report(report_harness, endpoint, query, output_mode):
    with report_harness.client as client:
        response = client.post(endpoint, json=_request(endpoint, query, output_mode))

    assert response.status_code == 403
    detail = response.json()["detail"]
    assert detail["code"] == "plan_feature_required"
    assert detail["feature"] == "deep_research"
    assert detail["plan"] == "free"
    assert report_harness.calls == [], "套餐检查必须发生在图执行之前"


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("plan,role", [
    ("pro", "user"), ("team", "user"), ("free", "admin"), ("free", "internal"),
])
def test_report_gate_uses_authenticated_paid_or_privileged_identity(report_harness, endpoint, plan, role):
    report_harness.plans.set_plan("alice", plan)
    report_harness.principal["value"] = Principal("alice", "alice@example.invalid", role=role, auth_type="api_key")
    with report_harness.client as client:
        response = client.post(endpoint, json=_request(endpoint, "分析 AAPL", "investment_report"))

    assert response.status_code == 200
    assert len(report_harness.calls) == 1
    assert report_harness.calls[0]["output_mode"] == "investment_report"


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_explicit_brief_override_remains_available_to_free_users(report_harness, endpoint):
    with report_harness.client as client:
        response = client.post(endpoint, json=_request(endpoint, "生成 AAPL 投资报告", "brief"))

    assert response.status_code == 200
    assert report_harness.calls[0]["output_mode"] == "brief"


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_new_default_request_resolves_to_brief_mode(report_harness, endpoint):
    with report_harness.client as client:
        response = client.post(endpoint, json={"query": "分析 AAPL"})

    assert response.status_code == 200
    assert report_harness.calls[0]["output_mode"] == "brief"


def test_free_default_request_cannot_inherit_checkpoint_report_mode(report_harness, monkeypatch):
    from backend.graph.runner import GraphRunner

    initial_state = importlib.import_module("backend.graph.nodes.build_initial_state")
    monkeypatch.setattr(initial_state, "load_memory_context", lambda **_kwargs: {})
    runner = GraphRunner.create()
    asyncio.run(runner._graph.aupdate_state(
        {"configurable": {"thread_id": "private:alice:default"}},
        {"output_mode": "investment_report"},
    ))
    output_modes = []

    async def run_graph(_runner, **kwargs):
        state = await runner.ainvoke(**kwargs)
        output_modes.append(state["output_mode"])
        return state

    monkeypatch.setattr(importlib.import_module("backend.graph.runner"), "run_graph_traced", run_graph)
    with report_harness.client as client:
        response = client.post("/chat/supervisor", json={"query": "你好"})

    assert response.status_code == 200
    assert output_modes == ["brief"]


@pytest.mark.parametrize("endpoint", ("/chat/supervisor", "/chat/supervisor/stream"))
def test_report_gate_checks_resolved_query_reference(report_harness, endpoint):
    report_harness.reference["query"] = "生成 AAPL 投资报告"
    with report_harness.client as client:
        response = client.post(endpoint, json={"query": "继续"})

    assert response.status_code == 403
    assert report_harness.calls == []


def test_free_user_cannot_request_deep_research_through_execution_depth(report_harness):
    with report_harness.client as client:
        response = client.post("/api/execute", json={
            "query": "分析 AAPL", "output_mode": "brief", "analysis_depth": "deep_research",
        })

    assert response.status_code == 403
    assert response.json()["detail"]["feature"] == "deep_research"
    assert report_harness.calls == []
