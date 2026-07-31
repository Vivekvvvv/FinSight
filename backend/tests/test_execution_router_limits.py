from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import execution_router
from backend.api.execution_router import ExecutionRouterDeps, create_execution_router
from backend.security.auth import Principal, get_current_user


def _client(monkeypatch, captured: dict) -> TestClient:
    async def _resume_graph_pipeline(**kwargs):
        captured.update(kwargs)
        yield {"type": "done"}

    async def _get_graph_runner():
        return object()

    monkeypatch.setattr(
        execution_router, "resume_graph_pipeline", _resume_graph_pipeline,
    )
    app = FastAPI()
    app.include_router(
        create_execution_router(
            ExecutionRouterDeps(
                get_graph_runner=_get_graph_runner,
                resolve_thread_id=lambda session_id: str(session_id),
                schedule_report_index=lambda **_kwargs: None,
                update_session_context=lambda **_kwargs: None,
                redact_sensitive_payload=lambda payload: payload,
                is_raw_trace_event=lambda _payload: False,
                contract_info=lambda: {},
                sse_event_schema_version="chat.sse.v1",
            )
        )
    )
    app.dependency_overrides[get_current_user] = lambda: Principal(
        user_id="alice", role="user", auth_type="api_key",
    )
    return TestClient(app)


def test_execute_resume_rejects_oversized_resume_value_before_runner(monkeypatch):
    captured: dict = {}
    with _client(monkeypatch, captured) as client:
        response = client.post(
            "/api/execute/resume",
            json={
                "thread_id": "private:alice:default",
                "resume_value": "x" * (64 * 1024),
            },
        )

    assert response.status_code == 422
    assert captured == {}


def test_execute_resume_preserves_valid_structured_value(monkeypatch):
    captured: dict = {}
    resume_value = {"action": "confirm", "parameters": {"depth": 2}}
    with _client(monkeypatch, captured) as client:
        response = client.post(
            "/api/execute/resume",
            json={
                "thread_id": "private:alice:default",
                "session_id": "private:alice:default",
                "run_id": "run-1",
                "source": "workbench",
                "resume_value": resume_value,
            },
        )

    assert response.status_code == 200
    assert captured["resume_value"] == resume_value
    assert captured["run_id"] == "run-1"
    assert captured["source"] == "workbench"


@pytest.mark.parametrize("field", ["thread_id", "session_id", "run_id", "source"])
def test_execute_resume_rejects_oversized_identifiers(monkeypatch, field):
    captured: dict = {}
    payload = {
        "thread_id": "private:alice:default",
        "resume_value": "confirm",
        field: "x" * 257,
    }
    with _client(monkeypatch, captured) as client:
        response = client.post("/api/execute/resume", json=payload)

    assert response.status_code == 422
    assert captured == {}


def test_execute_rejects_oversized_ticker_before_pipeline(monkeypatch):
    captured: dict = {}
    with _client(monkeypatch, captured) as client:
        response = client.post(
            "/api/execute",
            json={"query": "analyze", "tickers": ["A" * 33]},
        )

    assert response.status_code == 422
    assert captured == {}


def test_execute_rejects_oversized_agent_preferences_before_pipeline(monkeypatch):
    captured: dict = {}
    with _client(monkeypatch, captured) as client:
        response = client.post(
            "/api/execute",
            json={
                "query": "analyze",
                "agent_preferences": {"blob": "x" * (64 * 1024)},
            },
        )

    assert response.status_code == 422
    assert captured == {}


@pytest.mark.parametrize("field", ["session_id", "run_id", "source"])
def test_execute_rejects_oversized_identifiers_before_pipeline(monkeypatch, field):
    captured: dict = {}
    with _client(monkeypatch, captured) as client:
        response = client.post(
            "/api/execute",
            json={"query": "analyze", field: "x" * 257},
        )

    assert response.status_code == 422
    assert captured == {}


def test_execute_rejects_oversized_output_mode_before_pipeline(monkeypatch):
    captured: dict = {}
    with _client(monkeypatch, captured) as client:
        response = client.post(
            "/api/execute",
            json={"query": "analyze", "output_mode": "x" * 65},
        )

    assert response.status_code == 422
    assert captured == {}


def test_execute_rejects_oversized_agent_name_before_pipeline(monkeypatch):
    captured: dict = {}
    with _client(monkeypatch, captured) as client:
        response = client.post(
            "/api/execute",
            json={"query": "analyze", "agents": ["x" * 65]},
        )

    assert response.status_code == 422
    assert captured == {}
