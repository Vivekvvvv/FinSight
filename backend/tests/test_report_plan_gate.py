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
    checkpoint = {"values": {}}
    state_reads = []
    resume_calls = []

    class CheckpointRunner:
        async def aget_state(self, *, thread_id):
            state_reads.append(thread_id)
            return dict(checkpoint["values"])

        async def resume(self, **kwargs):
            resume_calls.append(kwargs)
            yield {"event": "on_chain_end", "data": {"output": {"artifacts": {"draft_markdown": "完成"}}}}

    runner = CheckpointRunner()

    async def get_runner():
        return runner

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
    monkeypatch.setattr(execution_router, "resume_graph_pipeline", pipeline)
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
    return SimpleNamespace(
        client=TestClient(app), plans=plans, principal=principal, calls=calls, reference=reference,
        runner=runner, checkpoint=checkpoint, state_reads=state_reads, resume_calls=resume_calls,
    )


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


@pytest.mark.parametrize("checkpoint", [
    {"output_mode": "investment_report"},
    {"query": "生成 AAPL 投资报告"},
    {"output_mode": "brief", "ui_context": {"analysis_depth": "deep_research"}},
])
def test_free_user_cannot_resume_report_or_deep_research_checkpoint(report_harness, checkpoint):
    report_harness.checkpoint["values"] = checkpoint
    with report_harness.client as client:
        response = client.post("/api/execute/resume", json={
            "thread_id": "private:alice:default", "resume_value": "Confirm execute",
        })

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "plan_feature_required"
    assert report_harness.calls == []
    assert report_harness.state_reads == ["private:alice:default"]


def test_resume_uses_current_plan_instead_of_checkpointed_privilege(report_harness):
    report_harness.plans.set_plan("alice", "pro")
    report_harness.checkpoint["values"] = {
        "output_mode": "investment_report",
        "ui_context": {"_authenticated_user": {"user_id": "alice", "role": "admin"}},
    }
    report_harness.plans.set_plan("alice", "free")
    with report_harness.client as client:
        response = client.post("/api/execute/resume", json={
            "thread_id": "private:alice:default",
            "resume_value": {"action": "confirm", "output_mode": "brief"},
        })

    assert response.status_code == 403
    assert response.json()["detail"]["plan"] == "free"
    assert report_harness.calls == []


def test_downgraded_user_cannot_advance_real_paused_report_checkpoint(report_harness, monkeypatch):
    from backend.graph.runner import GraphRunner

    initial_state = importlib.import_module("backend.graph.nodes.build_initial_state")
    monkeypatch.setattr(initial_state, "load_memory_context", lambda **_kwargs: {})
    runner = GraphRunner.create()
    thread_id = "private:alice:default"
    report_harness.plans.set_plan("alice", "pro")
    initial = asyncio.run(runner.ainvoke(
        thread_id=thread_id, query="Generate AAPL investment report",
        ui_context={"active_symbol": "AAPL"}, output_mode="investment_report",
        confirmation_mode="required",
    ))
    assert initial.get("__interrupt__")
    config = {"configurable": {"thread_id": thread_id}}
    before = asyncio.run(runner._graph.aget_state(config)).config
    monkeypatch.setattr(report_harness.runner, "aget_state", runner.aget_state)
    report_harness.plans.set_plan("alice", "free")

    with report_harness.client as client:
        response = client.post("/api/execute/resume", json={
            "thread_id": thread_id, "resume_value": "Confirm execute",
        })

    assert response.status_code == 403
    assert report_harness.calls == []
    assert asyncio.run(runner._graph.aget_state(config)).config == before


@pytest.mark.parametrize("plan,role", [
    ("pro", "user"), ("team", "user"), ("free", "admin"), ("free", "internal"),
])
def test_paid_or_privileged_user_can_resume_report_checkpoint(report_harness, plan, role):
    report_harness.plans.set_plan("alice", plan)
    report_harness.principal["value"] = Principal("alice", "alice@example.invalid", role=role, auth_type="api_key")
    report_harness.checkpoint["values"] = {"output_mode": "investment_report"}
    with report_harness.client as client:
        response = client.post("/api/execute/resume", json={
            "thread_id": "private:alice:default", "resume_value": "Confirm execute",
        })

    assert response.status_code == 200
    assert report_harness.calls[0]["thread_id"] == "private:alice:default"
    assert report_harness.calls[0]["resume_value"] == "Confirm execute"


@pytest.mark.parametrize("output_mode", ["brief", "chat"])
def test_free_user_can_resume_non_report_checkpoint(report_harness, output_mode):
    report_harness.checkpoint["values"] = {"output_mode": output_mode}
    with report_harness.client as client:
        response = client.post("/api/execute/resume", json={
            "thread_id": "private:alice:default", "resume_value": "Confirm execute",
        })

    assert response.status_code == 200
    assert len(report_harness.calls) == 1


def test_unreadable_resume_checkpoint_does_not_skip_authorization(report_harness, monkeypatch):
    async def fail_read(**_kwargs):
        raise RuntimeError("checkpoint unavailable")

    monkeypatch.setattr(report_harness.runner, "aget_state", fail_read)
    with TestClient(report_harness.client.app, raise_server_exceptions=False) as client:
        response = client.post("/api/execute/resume", json={
            "thread_id": "private:alice:default", "resume_value": "Confirm execute",
        })

    assert response.status_code == 500
    assert report_harness.calls == []


@pytest.mark.parametrize("change", ["checkpoint", "plan"])
def test_resume_rechecks_authorization_under_execution_lock_before_advancing(report_harness, monkeypatch, change):
    from backend.api import execution_router
    from backend.services import execution_service
    from backend.services.execution_helpers import _get_thread_run_lock

    if change == "plan":
        report_harness.plans.set_plan("alice", "pro")

    async def changed_checkpoint(*, thread_id):
        assert _get_thread_run_lock(thread_id).locked(), "读取与恢复必须受同一会话锁保护"
        report_harness.state_reads.append(thread_id)
        if change == "plan":
            if len(report_harness.state_reads) == 2:
                report_harness.plans.set_plan("alice", "free")
            return {"output_mode": "investment_report"}
        return {"output_mode": "brief" if len(report_harness.state_reads) == 1 else "investment_report"}

    monkeypatch.setattr(report_harness.runner, "aget_state", changed_checkpoint)
    monkeypatch.setattr(execution_router, "resume_graph_pipeline", execution_service.resume_graph_pipeline)
    with report_harness.client as client:
        response = client.post("/api/execute/resume", json={
            "thread_id": "private:alice:default", "resume_value": "Confirm execute",
        })

    assert response.status_code == 200
    assert '"type": "error"' in response.text
    assert report_harness.state_reads == ["private:alice:default", "private:alice:default"]
    assert report_harness.resume_calls == [], "预检查后的 checkpoint 变化不能绕过权限"
