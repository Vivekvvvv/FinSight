# -*- coding: utf-8 -*-
"""报告对象构建失败时不能对外说“质量通过/可发布”。

chat_router 此前 except 后只把 report 置 None，``apply_quality_to_report(None)``
默认返回 state=pass，响应仍是 publishable=True——前端会把一次失败渲染成
“质检通过”，且没有任何字段能说明报告缺失（项目规则 2）。
"""
from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.chat_router import ChatRouterDeps, create_chat_router
from backend.security.auth import Principal, get_current_user

_SESSION_ID = "private:router-test:default"


class _FakeRunner:
    async def ainvoke(self, **_kwargs):
        return {
            "artifacts": {"draft_markdown": "## 结论\n- 继续观察"},
            "subject": {"tickers": ["AAPL"]},
            "trace": [],
        }


def _client() -> TestClient:
    async def _get_graph_runner():
        return _FakeRunner()

    deps = ChatRouterDeps(
        get_graph_runner=_get_graph_runner,
        resolve_thread_id=lambda session_id: session_id,
        build_ui_context=lambda _request: {},
        resolve_query_reference=lambda query, _thread_id: query,
        schedule_report_index=lambda **_kwargs: None,
        update_session_context=lambda **_kwargs: None,
        contract_info=lambda: {},
        resolve_trace_raw_enabled=lambda _request: False,
        is_raw_trace_event=lambda _event: False,
        redact_sensitive_payload=lambda value: value,
        get_session_context=lambda _thread_id: SimpleNamespace(clear=lambda: None, add_turn=lambda **_kwargs: None),
        chat_history_store=SimpleNamespace(append_turn=lambda **_kwargs: None),
        chat_response_schema_version="test",
        sse_event_schema_version="test",
    )
    app = FastAPI()
    app.include_router(create_chat_router(deps))
    app.dependency_overrides[get_current_user] = lambda: Principal(
        user_id="router-test", role="user", auth_type="jwt",
    )
    return TestClient(app)


def _post(client: TestClient) -> dict:
    response = client.post(
        "/chat/supervisor",
        json={"query": "分析 AAPL", "session_id": _SESSION_ID},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_report_build_failure_is_explicit_not_silent_pass(monkeypatch):
    import backend.graph.report_builder as report_builder

    def _boom(**_kwargs):
        raise RuntimeError("builder exploded")

    monkeypatch.setattr(report_builder, "build_report_payload", _boom)

    with _client() as client:
        body = _post(client)

    assert body["success"] is True
    assert body["report"] is None
    assert body["report_unavailable"] is True
    assert body["publishable"] is False
    assert body["quality"]["state"] != "pass"


def test_successful_report_build_stays_publishable(monkeypatch):
    import backend.graph.report_builder as report_builder

    monkeypatch.setattr(
        report_builder,
        "build_report_payload",
        lambda **_kwargs: {"title": "AAPL 研究报告", "sections": [], "citations": []},
    )

    with _client() as client:
        body = _post(client)

    assert body["report_unavailable"] is False
    assert body["publishable"] is True
    assert body["quality"]["state"] == "pass"
