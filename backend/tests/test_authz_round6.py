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
