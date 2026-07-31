from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.chat_router import ChatRouterDeps, create_chat_router
from backend.security.auth import Principal, get_current_user, require_admin_principal


_SESSION_ID = "private:router-test:default"


def _chat_client(resolve_thread_id):
    async def _get_graph_runner():
        return object()

    deps = ChatRouterDeps(
        get_graph_runner=_get_graph_runner,
        resolve_thread_id=resolve_thread_id,
        build_ui_context=lambda _request: {},
        resolve_query_reference=lambda query, _thread_id: query,
        schedule_report_index=lambda **_kwargs: None,
        update_session_context=lambda **_kwargs: None,
        contract_info=lambda: {},
        resolve_trace_raw_enabled=lambda _request: False,
        is_raw_trace_event=lambda _event: False,
        redact_sensitive_payload=lambda value: value,
        get_session_context=lambda _thread_id: SimpleNamespace(clear=lambda: None, add_turn=lambda **_kwargs: None),
        chat_history_store=SimpleNamespace(
            list_messages=lambda **_kwargs: [],
            clear=lambda **_kwargs: None,
            append_turn=lambda **_kwargs: None,
        ),
        chat_response_schema_version="test",
        sse_event_schema_version="test",
    )
    app = FastAPI()
    app.include_router(create_chat_router(deps))
    app.dependency_overrides[get_current_user] = lambda: Principal(
        user_id="router-test",
        role="user",
        auth_type="jwt",
    )
    return TestClient(app)


def _raise_private_value_error(_session_id):
    raise ValueError("PRIVATE C:/secret/session-index.json")


def _report_client(resolve_thread_id):
    from backend.api.report_router import ReportRouterDeps, create_report_router

    app = FastAPI()
    app.include_router(
        create_report_router(
            ReportRouterDeps(
                resolve_thread_id=resolve_thread_id,
                get_report_index_store=lambda: object(),
            )
        )
    )
    app.dependency_overrides[get_current_user] = lambda: Principal(
        user_id="router-test",
        role="user",
        auth_type="jwt",
    )
    return TestClient(app)


def test_chat_supervisor_value_error_is_redacted():
    with _chat_client(_raise_private_value_error) as client:
        response = client.post(
            "/chat/supervisor",
            json={"query": "hello", "session_id": _SESSION_ID},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid session_id"
    assert "C:/secret/session-index.json" not in response.text


def test_chat_supervisor_stream_value_error_is_redacted():
    with _chat_client(_raise_private_value_error) as client:
        response = client.post(
            "/chat/supervisor/stream",
            json={"query": "hello", "session_id": _SESSION_ID},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid session_id"
    assert "C:/secret/session-index.json" not in response.text


def test_chat_history_list_value_error_is_redacted():
    with _chat_client(_raise_private_value_error) as client:
        response = client.get("/api/chat/history", params={"session_id": _SESSION_ID})

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid session_id"
    assert "C:/secret/session-index.json" not in response.text


def test_chat_history_clear_value_error_is_redacted():
    with _chat_client(_raise_private_value_error) as client:
        response = client.delete("/api/chat/history", params={"session_id": _SESSION_ID})

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid session_id"
    assert "C:/secret/session-index.json" not in response.text


def test_chat_add_chart_value_error_is_redacted():
    with _chat_client(_raise_private_value_error) as client:
        response = client.post(
            "/api/chat/add-chart-data",
            json={
                "session_id": _SESSION_ID,
                "ticker": "AAPL",
                "summary": "chart summary",
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid session_id"
    assert "C:/secret/session-index.json" not in response.text


def test_entitlement_set_plan_value_error_is_redacted(monkeypatch):
    from backend.api import entitlements_router

    service = SimpleNamespace(
        set_plan=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("PRIVATE C:/secret/entitlements.json")
        ),
    )
    monkeypatch.setattr(entitlements_router, "get_entitlements_service", lambda: service)
    app = FastAPI()
    app.include_router(entitlements_router.create_entitlements_router())
    app.dependency_overrides[require_admin_principal] = lambda: Principal(
        user_id="admin",
        role="admin",
        auth_type="jwt",
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/admin/entitlements/plan",
            json={"user_id": "target", "plan": "pro"},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid entitlement request"
    assert "C:/secret/entitlements.json" not in response.text


def test_execute_value_error_is_redacted():
    from backend.api.execution_router import ExecutionRouterDeps, create_execution_router

    async def _get_graph_runner():
        return object()

    deps = ExecutionRouterDeps(
        get_graph_runner=_get_graph_runner,
        resolve_thread_id=_raise_private_value_error,
        schedule_report_index=lambda **_kwargs: None,
        update_session_context=lambda **_kwargs: None,
        redact_sensitive_payload=lambda value: value,
        is_raw_trace_event=lambda _event: False,
        contract_info=lambda: {},
        sse_event_schema_version="test",
    )
    app = FastAPI()
    app.include_router(create_execution_router(deps))
    app.dependency_overrides[get_current_user] = lambda: Principal(
        user_id="router-test",
        role="user",
        auth_type="jwt",
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/execute",
            json={"query": "hello", "session_id": _SESSION_ID},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid session_id"
    assert "C:/secret/session-index.json" not in response.text


def test_morning_brief_value_error_is_redacted():
    from backend.api.morning_brief_router import MorningBriefRouterDeps, create_morning_brief_router

    deps = MorningBriefRouterDeps(
        resolve_thread_id=_raise_private_value_error,
        get_portfolio_positions=lambda _session_id: [],
        get_stock_price=lambda _ticker: None,
        get_company_news=lambda _ticker, _limit: None,
    )
    app = FastAPI()
    app.include_router(create_morning_brief_router(deps))
    app.dependency_overrides[get_current_user] = lambda: Principal(
        user_id="router-test",
        role="user",
        auth_type="jwt",
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/morning-brief/generate",
            json={"session_id": _SESSION_ID, "tickers": ["AAPL"]},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid session_id"
    assert "C:/secret/session-index.json" not in response.text


def test_report_index_value_error_is_redacted():
    with _report_client(_raise_private_value_error) as client:
        response = client.get("/api/reports/index", params={"session_id": _SESSION_ID})

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid session_id"
    assert "C:/secret/session-index.json" not in response.text


def test_report_replay_value_error_is_redacted():
    with _report_client(_raise_private_value_error) as client:
        response = client.get(
            "/api/reports/replay/report-1",
            params={"session_id": _SESSION_ID},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid session_id"
    assert "C:/secret/session-index.json" not in response.text


def test_report_citations_value_error_is_redacted():
    with _report_client(_raise_private_value_error) as client:
        response = client.get("/api/reports/citations", params={"session_id": _SESSION_ID})

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid session_id"
    assert "C:/secret/session-index.json" not in response.text


def test_report_favorite_value_error_is_redacted():
    with _report_client(_raise_private_value_error) as client:
        response = client.post(
            "/api/reports/report-1/favorite",
            json={"session_id": _SESSION_ID, "is_favorite": True},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid session_id"
    assert "C:/secret/session-index.json" not in response.text


def test_report_note_value_error_is_redacted():
    with _report_client(_raise_private_value_error) as client:
        response = client.patch(
            "/api/reports/report-1/note",
            json={"session_id": _SESSION_ID, "user_note": "note"},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid session_id"
    assert "C:/secret/session-index.json" not in response.text


def test_report_compare_value_error_is_redacted():
    with _report_client(_raise_private_value_error) as client:
        response = client.get(
            "/api/reports/compare",
            params={"session_id": _SESSION_ID, "id1": "report-1", "id2": "report-2"},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid session_id"
    assert "C:/secret/session-index.json" not in response.text


def test_report_review_status_value_error_is_redacted():
    with _report_client(_raise_private_value_error) as client:
        response = client.patch(
            "/api/reports/report-1/review_status",
            json={"session_id": _SESSION_ID, "review_status": "reviewed"},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid session_id"
    assert "C:/secret/session-index.json" not in response.text


def test_report_tags_value_error_is_redacted():
    with _report_client(_raise_private_value_error) as client:
        response = client.patch(
            "/api/reports/report-1/tags",
            json={"session_id": _SESSION_ID, "tags": ["watch"]},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid session_id"
    assert "C:/secret/session-index.json" not in response.text


def test_report_tags_rejects_excessive_count():
    with _report_client(lambda session_id: session_id) as client:
        response = client.patch(
            "/api/reports/report-1/tags",
            json={"session_id": _SESSION_ID, "tags": [f"tag-{i}" for i in range(21)]},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "too many tags"


def test_report_tags_rejects_oversized_or_non_string_tag():
    with _report_client(lambda session_id: session_id) as client:
        oversized = client.patch(
            "/api/reports/report-1/tags",
            json={"session_id": _SESSION_ID, "tags": ["x" * 65]},
        )
        non_string = client.patch(
            "/api/reports/report-1/tags",
            json={"session_id": _SESSION_ID, "tags": [{"nested": "value"}]},
        )

    assert oversized.status_code == 422
    assert oversized.json()["detail"] == "invalid tag"
    assert non_string.status_code == 422
    assert non_string.json()["detail"] == "invalid tag"


def test_report_viewed_value_error_is_redacted():
    with _report_client(_raise_private_value_error) as client:
        response = client.post(
            "/api/reports/report-1/viewed",
            json={"session_id": _SESSION_ID},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid session_id"
    assert "C:/secret/session-index.json" not in response.text


def test_daily_tasks_value_error_is_redacted():
    from backend.api.task_router import TaskRouterDeps, create_task_router

    deps = TaskRouterDeps(
        resolve_thread_id=_raise_private_value_error,
        get_report_index_store=lambda: object(),
        get_portfolio_positions=lambda _session_id: [],
        get_stock_price=lambda _ticker: None,
    )
    app = FastAPI()
    app.include_router(create_task_router(deps))
    app.dependency_overrides[get_current_user] = lambda: Principal(
        user_id="router-test",
        role="user",
        auth_type="jwt",
    )

    with TestClient(app) as client:
        response = client.get("/api/tasks/daily", params={"session_id": _SESSION_ID})

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid session_id"
    assert "C:/secret/session-index.json" not in response.text
