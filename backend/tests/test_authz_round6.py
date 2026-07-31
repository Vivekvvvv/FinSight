# -*- coding: utf-8 -*-
"""A 类越权修复回归（docs/BUG_AUDIT_2026-07-04.md）—— 生产模式下拒绝伪造身份。

dev 模式（DEV_MODE=1，测试默认）下 require_matching_identity 放行，测不到越权拒绝；
这里显式切到 prod 主体（release-key-1 → alice），传他人身份，期望 403。
范式同 backend/tests/test_auth_principal.py。
"""
from __future__ import annotations

from fastapi.testclient import TestClient


def _set_prod_env(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "0")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_BASE", "https://example.invalid/v1")
    monkeypatch.setenv("POSTGRES_DB", "test")
    monkeypatch.setenv("POSTGRES_USER", "test")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("API_AUTH_KEYS", "release-key-1")
    monkeypatch.setenv(
        "API_AUTH_PRINCIPALS",
        '{"release-key-1":{"user_id":"alice","email":"alice@example.invalid","role":"user"}}',
    )


def _client(monkeypatch) -> TestClient:
    from backend.api import main

    _set_prod_env(monkeypatch)
    monkeypatch.setattr(
        main, "_rate_limiter",
        main.SimpleRateLimiter(limit_per_window=100, window_seconds=60, enabled=False),
    )
    return TestClient(main.app)


_KEY = {"x-api-key": "release-key-1"}


def test_a4_alerts_feed_rejects_forged_email(monkeypatch):
    with _client(monkeypatch) as client:
        resp = client.get("/api/alerts/feed", params={"email": "bob@example.invalid"}, headers=_KEY)
    assert resp.status_code == 403


def test_a3_agent_preferences_get_rejects_forged_user_id(monkeypatch):
    with _client(monkeypatch) as client:
        resp = client.get("/api/agents/preferences", params={"user_id": "bob"}, headers=_KEY)
    assert resp.status_code == 403


def test_a3_agent_preferences_put_rejects_forged_user_id(monkeypatch):
    with _client(monkeypatch) as client:
        resp = client.put(
            "/api/agents/preferences",
            json={"user_id": "bob", "preferences": {"maxRounds": 5}},
            headers=_KEY,
        )
    assert resp.status_code == 403


def test_a7_what_changed_rejects_forged_user_id_with_valid_session(monkeypatch):
    with _client(monkeypatch) as client:
        # session_id 正确（alice 自己的），但 user_id 伪造为 bob → 必须拒绝
        resp = client.get(
            "/api/what-changed",
            params={"session_id": "private:alice:default", "user_id": "bob"},
            headers=_KEY,
        )
    assert resp.status_code == 403


def test_what_changed_rejects_oversized_symbol_before_aggregation(monkeypatch):
    from backend.api import what_changed_router

    calls = []

    def fake_get_what_changed(**kwargs):
        calls.append(kwargs)
        return []

    monkeypatch.setattr(what_changed_router.what_changed, "get_what_changed", fake_get_what_changed)
    with _client(monkeypatch) as client:
        response = client.get(
            "/api/what-changed",
            params={"session_id": "private:alice:default", "symbol": "A" * 33},
            headers=_KEY,
        )

    assert response.status_code == 422
    assert calls == []


def test_research_quality_rejects_forged_user_id_with_valid_session(monkeypatch):
    with _client(monkeypatch) as client:
        resp = client.get(
            "/api/research-quality",
            params={"session_id": "private:alice:default", "user_id": "bob"},
            headers=_KEY,
        )

    assert resp.status_code == 403


def test_research_quality_default_user_uses_authenticated_principal(monkeypatch):
    from backend.api import research_quality_router

    captured = {}

    def fake_get_research_quality(**kwargs):
        captured.update(kwargs)
        return {"success": True, "summary": {}, "top_issues": [], "next_actions": []}

    monkeypatch.setattr(
        research_quality_router.research_quality,
        "get_research_quality",
        fake_get_research_quality,
    )

    with _client(monkeypatch) as client:
        resp = client.get(
            "/api/research-quality",
            params={"session_id": "private:alice:default"},
            headers=_KEY,
        )

    assert resp.status_code == 200
    assert captured["user_id"] == "alice"


def test_research_quality_rejects_oversized_symbol_before_service(monkeypatch):
    from backend.api import research_quality_router

    calls = []

    def fake_get_research_quality(**kwargs):
        calls.append(kwargs)
        return {"success": True}

    monkeypatch.setattr(
        research_quality_router.research_quality,
        "get_research_quality",
        fake_get_research_quality,
    )
    with _client(monkeypatch) as client:
        response = client.get(
            "/api/research-quality",
            params={"session_id": "private:alice:default", "symbol": "A" * 33},
            headers=_KEY,
        )

    assert response.status_code == 422
    assert calls == []


def test_a6_today_rejects_forged_session_id(monkeypatch):
    with _client(monkeypatch) as client:
        resp = client.get(
            "/api/today",
            params={"session_id": "private:bob:default"},
            headers=_KEY,
        )
    assert resp.status_code == 403


def test_a10_risk_lens_rejects_forged_session_id(monkeypatch):
    with _client(monkeypatch) as client:
        resp = client.get(
            "/api/portfolio/risk-lens",
            params={"session_id": "private:bob:default"},
            headers=_KEY,
        )
    assert resp.status_code == 403


def test_a10_risk_lens_history_rejects_forged_session_id(monkeypatch):
    with _client(monkeypatch) as client:
        resp = client.get(
            "/api/portfolio/risk-lens/history",
            params={"session_id": "private:bob:default"},
            headers=_KEY,
        )
    assert resp.status_code == 403


def test_a10_risk_history_default_user_uses_authenticated_principal(monkeypatch):
    from backend.api import risk_lens_router

    captured = {}

    def fake_get_risk_snapshots_history(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(
        risk_lens_router,
        "get_risk_snapshots_history",
        fake_get_risk_snapshots_history,
    )

    with _client(monkeypatch) as client:
        resp = client.get(
            "/api/portfolio/risk-lens/history",
            params={"session_id": "private:alice:default"},
            headers=_KEY,
        )

    assert resp.status_code == 200
    assert captured["user_id"] == "alice"


def test_a11_timeline_rejects_forged_session_id(monkeypatch):
    # timeline_service 的报告事件仅按 session_id 过滤，此前只校验 user_id，
    # 传自己的 user_id + 他人 session_id 即可读到他人报告时间线（R47 修复）。
    with _client(monkeypatch) as client:
        resp = client.get(
            "/api/timeline/AAPL",
            params={"session_id": "private:bob:default"},
            headers=_KEY,
        )
    assert resp.status_code == 403


def test_a11_timeline_default_user_uses_authenticated_principal(monkeypatch):
    from backend.api import timeline_router

    captured = {}

    def fake_get_timeline(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(timeline_router.timeline_service, "get_timeline", fake_get_timeline)

    with _client(monkeypatch) as client:
        resp = client.get(
            "/api/timeline/AAPL",
            params={"session_id": "private:alice:default"},
            headers=_KEY,
        )

    assert resp.status_code == 200
    assert captured["user_id"] == "alice"


def test_a1_chat_history_get_rejects_forged_session_id(monkeypatch):
    with _client(monkeypatch) as client:
        resp = client.get(
            "/api/chat/history",
            params={"session_id": "private:bob:default"},
            headers=_KEY,
        )
    assert resp.status_code == 403


def test_a2_chat_history_delete_rejects_forged_session_id(monkeypatch):
    with _client(monkeypatch) as client:
        resp = client.delete(
            "/api/chat/history",
            params={"session_id": "private:bob:default"},
            headers=_KEY,
        )
    assert resp.status_code == 403


def test_execute_rejects_forged_session_id(monkeypatch):
    from backend.api import execution_router

    async def fake_run_graph_pipeline(**_kwargs):
        yield {"type": "done"}

    monkeypatch.setattr(execution_router, "run_graph_pipeline", fake_run_graph_pipeline)

    with _client(monkeypatch) as client:
        resp = client.post(
            "/api/execute",
            json={"query": "test", "session_id": "private:bob:default"},
            headers=_KEY,
        )

    assert resp.status_code == 403


def test_execute_resume_rejects_forged_thread_id(monkeypatch):
    from backend.api import execution_router

    async def fake_resume_graph_pipeline(**_kwargs):
        yield {"type": "done"}

    monkeypatch.setattr(execution_router, "resume_graph_pipeline", fake_resume_graph_pipeline)

    with _client(monkeypatch) as client:
        resp = client.post(
            "/api/execute/resume",
            json={"thread_id": "private:bob:default", "resume_value": "confirm"},
            headers=_KEY,
        )

    assert resp.status_code == 403


def test_chat_supervisor_rejects_forged_session_id(monkeypatch):
    from backend.graph import runner as graph_runner

    async def fake_run_graph_traced(*_args, **_kwargs):
        return {"artifacts": {"draft_markdown": "ok"}, "trace": []}

    monkeypatch.setattr(graph_runner, "run_graph_traced", fake_run_graph_traced)

    with _client(monkeypatch) as client:
        resp = client.post(
            "/chat/supervisor",
            json={"query": "test", "session_id": "private:bob:default"},
            headers=_KEY,
        )

    assert resp.status_code == 403


def test_chat_supervisor_stream_rejects_forged_session_id(monkeypatch):
    from backend.services import execution_service

    async def fake_run_graph_pipeline(**_kwargs):
        yield {"type": "done"}

    monkeypatch.setattr(execution_service, "run_graph_pipeline", fake_run_graph_pipeline)

    with _client(monkeypatch) as client:
        resp = client.post(
            "/chat/supervisor/stream",
            json={"query": "test", "session_id": "private:bob:default"},
            headers=_KEY,
        )

    assert resp.status_code == 403


def test_chat_add_chart_data_rejects_forged_session_id(monkeypatch):
    with _client(monkeypatch) as client:
        resp = client.post(
            "/api/chat/add-chart-data",
            json={
                "ticker": "AAPL",
                "summary": "forged chart context",
                "session_id": "private:bob:default",
            },
            headers=_KEY,
        )

    assert resp.status_code == 403
