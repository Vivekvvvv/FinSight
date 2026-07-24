from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient


def _set_prod_env(monkeypatch, *, role: str = "user") -> None:
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
        '{"release-key-1":{"user_id":"alice","email":"alice@example.invalid","role":"' + role + '"}}',
    )


def test_subscription_list_without_email_uses_principal_email(monkeypatch, tmp_path):
    from backend.api import main
    from backend.services import subscription_service as subs

    _set_prod_env(monkeypatch)
    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", tmp_path / "subscriptions.json")
    subs._subscription_service = None  # type: ignore[attr-defined]
    monkeypatch.setattr(main, "_rate_limiter", main.SimpleRateLimiter(limit_per_window=100, window_seconds=60, enabled=False))

    with TestClient(main.app) as client:
        response = client.get("/api/subscriptions", headers={"x-api-key": "release-key-1"})

    assert response.status_code == 200
    assert response.json()["subscriptions"] == []


def test_admin_subscription_list_requires_admin(monkeypatch, tmp_path):
    from backend.api import main
    from backend.services import subscription_service as subs

    _set_prod_env(monkeypatch, role="user")
    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", tmp_path / "subscriptions.json")
    subs._subscription_service = None  # type: ignore[attr-defined]
    monkeypatch.setattr(main, "_rate_limiter", main.SimpleRateLimiter(limit_per_window=100, window_seconds=60, enabled=False))

    with TestClient(main.app) as client:
        response = client.get("/api/admin/subscriptions", headers={"x-api-key": "release-key-1"})

    assert response.status_code == 403


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("POST", "/api/subscribe", {"email": "alice@example.invalid", "ticker": "AAPL"}),
        ("POST", "/api/unsubscribe", {"email": "alice@example.invalid", "ticker": "AAPL"}),
        ("GET", "/api/subscriptions", None),
        (
            "POST",
            "/api/subscription/toggle",
            {"email": "alice@example.invalid", "ticker": "AAPL", "enabled": True},
        ),
        ("GET", "/api/admin/subscriptions", None),
    ],
)
def test_subscription_internal_errors_are_redacted(monkeypatch, method, path, payload, caplog, capsys):
    from backend.api import main
    from backend.services import subscription_service as subs

    class FailingSubscriptionService:
        @staticmethod
        def is_valid_email(_email):
            return True

        @staticmethod
        def fail(*_args, **_kwargs):
            raise RuntimeError("private subscription storage detail")

        subscribe = fail
        unsubscribe = fail
        get_subscriptions = fail
        toggle_subscription = fail

    _set_prod_env(monkeypatch, role="admin")
    monkeypatch.setattr(subs, "get_subscription_service", lambda: FailingSubscriptionService())
    monkeypatch.setattr(main, "_rate_limiter", main.SimpleRateLimiter(limit_per_window=100, window_seconds=60, enabled=False))
    caplog.set_level(logging.ERROR, logger="backend.api.subscription_router")

    with TestClient(main.app) as client:
        response = client.request(
            method,
            path,
            headers={"x-api-key": "release-key-1"},
            json=payload,
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"
    assert "private subscription storage detail" not in response.text
    assert "private subscription storage detail" not in capsys.readouterr().err
    assert "private subscription storage detail" not in caplog.text
    assert "RuntimeError" in caplog.text
