"""聊天提醒必须使用认证邮箱，且不能继承上一轮的提醒身份。"""

import importlib
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.chat_router import ChatRouterDeps, create_chat_router
from backend.api.session_context import _build_ui_context, _resolve_thread_id
from backend.security.auth import Principal, get_current_user


@pytest.fixture
def chat_harness(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "0")
    principal = {"value": Principal("alice", "alice@example.invalid", auth_type="api_key")}
    calls = []
    runner_calls = []

    async def get_runner():
        runner_calls.append(True)
        return object()

    async def run_graph(_runner, **kwargs):
        calls.append(kwargs)
        return {"artifacts": {"draft_markdown": "提醒处理完成"}}

    async def pipeline(**kwargs):
        calls.append(kwargs)
        yield {"type": "done"}

    monkeypatch.setattr(importlib.import_module("backend.graph.runner"), "run_graph_traced", run_graph)
    monkeypatch.setattr(importlib.import_module("backend.services.execution_service"), "run_graph_pipeline", pipeline)
    monkeypatch.setattr(importlib.import_module("backend.graph.report_builder"), "build_report_payload", lambda **_kwargs: None)

    deps = ChatRouterDeps(
        get_graph_runner=get_runner,
        resolve_thread_id=_resolve_thread_id,
        build_ui_context=_build_ui_context,
        resolve_query_reference=lambda query, _thread: query,
        schedule_report_index=lambda **_kwargs: None,
        update_session_context=lambda **_kwargs: None,
        contract_info=lambda: {},
        resolve_trace_raw_enabled=lambda _request: False,
        is_raw_trace_event=lambda _event: False,
        redact_sensitive_payload=lambda payload: payload,
        get_session_context=lambda _thread: None,
        chat_history_store=None,
        chat_response_schema_version="chat.response.v1",
        sse_event_schema_version="chat.sse.v1",
    )
    app = FastAPI()
    app.include_router(create_chat_router(deps))
    app.dependency_overrides[get_current_user] = lambda: principal["value"]
    return SimpleNamespace(client=TestClient(app), principal=principal, calls=calls, runner_calls=runner_calls)


@pytest.mark.parametrize("endpoint", ["/chat/supervisor", "/chat/supervisor/stream"])
def test_chat_rejects_another_users_alert_email_before_execution(chat_harness, endpoint):
    with chat_harness.client as client:
        response = client.post(endpoint, json={
            "query": "AAPL 涨到 200 提醒我",
            "session_id": "private:alice:default",
            "context": {"user_email": "bob@example.invalid"},
        })

    assert response.status_code == 403
    assert "user_email" in response.json()["detail"]
    assert chat_harness.runner_calls == []
    assert chat_harness.calls == []


@pytest.mark.parametrize("endpoint", ["/chat/supervisor", "/chat/supervisor/stream"])
@pytest.mark.parametrize("provided_email", [None, "alice@example.invalid"])
def test_chat_uses_authenticated_alert_email(chat_harness, endpoint, provided_email):
    context = {"active_symbol": "AAPL"}
    if provided_email is not None:
        context["user_email"] = provided_email
    with chat_harness.client as client:
        response = client.post(endpoint, json={"query": "AAPL 涨到 200 提醒我", "context": context})

    assert response.status_code == 200
    assert len(chat_harness.calls) == 1
    assert chat_harness.calls[0]["thread_id"] == "private:alice:default"
    assert chat_harness.calls[0]["ui_context"]["user_email"] == "alice@example.invalid"
    assert chat_harness.calls[0]["ui_context"]["active_symbol"] == "AAPL"


@pytest.mark.parametrize("endpoint", ["/chat/supervisor", "/chat/supervisor/stream"])
def test_chat_without_authenticated_email_rejects_supplied_email(chat_harness, endpoint):
    chat_harness.principal["value"] = Principal("alice", None, auth_type="api_key")
    with chat_harness.client as client:
        response = client.post(endpoint, json={
            "query": "AAPL 涨到 200 提醒我",
            "context": {"user_email": "bob@example.invalid"},
        })

    assert response.status_code == 403
    assert chat_harness.calls == []


@pytest.mark.parametrize("endpoint", ["/chat/supervisor", "/chat/supervisor/stream"])
def test_dev_chat_keeps_explicit_alert_email(chat_harness, endpoint):
    chat_harness.principal["value"] = Principal("alice", "dev@example.invalid", auth_type="dev")
    with chat_harness.client as client:
        response = client.post(endpoint, json={
            "query": "AAPL 涨到 200 提醒我",
            "session_id": "public:alice:dev-thread",
            "context": {"user_email": "custom@example.invalid"},
        })

    assert response.status_code == 200
    assert chat_harness.calls[0]["ui_context"]["user_email"] == "custom@example.invalid"
    assert chat_harness.calls[0]["thread_id"] == "public:alice:dev-thread"


@pytest.mark.asyncio
@pytest.mark.parametrize("ui_context", [None, {}, {"user_email": ""}])
async def test_new_graph_run_cannot_reuse_checkpointed_alert_email(monkeypatch, ui_context):
    from backend.graph.runner import GraphRunner

    initial_state = importlib.import_module("backend.graph.nodes.build_initial_state")
    monkeypatch.setattr(initial_state, "load_memory_context", lambda **_kwargs: {})
    runner = GraphRunner.create()
    thread_id = "private:alice:default"
    # 真实 checkpoint 中可能已有修复前被客户端写入的其他用户邮箱。
    await runner._graph.aupdate_state(
        {"configurable": {"thread_id": thread_id}},
        {"user_email": "bob@example.invalid"},
    )

    state = await runner.ainvoke(thread_id=thread_id, query="你好", ui_context=ui_context)

    assert not state.get("user_email"), "本轮未提供提醒身份时必须清除旧 checkpoint 邮箱"
