from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _set_required_production_env(monkeypatch):
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_BASE", "https://example.invalid/v1")
    monkeypatch.setenv("POSTGRES_DB", "test")
    monkeypatch.setenv("POSTGRES_USER", "test")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test")
    monkeypatch.setenv("JWT_SECRET", "test-secret")


def test_security_gate_rejects_missing_api_key_when_enabled(monkeypatch):
    from backend.api import main

    monkeypatch.setenv("DEV_MODE", "0")
    _set_required_production_env(monkeypatch)
    monkeypatch.setenv("API_AUTH_KEYS", "release-key-1")
    monkeypatch.setattr(main, "_rate_limiter", main.SimpleRateLimiter(limit_per_window=100, window_seconds=60, enabled=False))

    with TestClient(main.app) as client:
        response = client.get("/api/user/profile", params={"user_id": "auth-check"})

    assert response.status_code == 401
    assert response.json().get("detail") == "Unauthorized"


def test_security_gate_returns_503_when_auth_enabled_without_keys(monkeypatch):
    from backend.api import main

    monkeypatch.setenv("DEV_MODE", "0")
    _set_required_production_env(monkeypatch)
    monkeypatch.delenv("API_AUTH_KEYS", raising=False)
    monkeypatch.delenv("API_AUTH_KEY", raising=False)
    monkeypatch.setattr(main, "_rate_limiter", main.SimpleRateLimiter(limit_per_window=100, window_seconds=60, enabled=False))

    with pytest.raises(SystemExit) as exc_info:
        main._validate_production_runtime_config()

    assert "API_AUTH_KEYS" in str(exc_info.value)


def test_security_gate_allowlisted_path_bypasses_auth(monkeypatch):
    from backend.api import main

    monkeypatch.setenv("DEV_MODE", "0")
    _set_required_production_env(monkeypatch)
    monkeypatch.setenv("API_AUTH_KEYS", "release-key-1")
    monkeypatch.setattr(main, "_rate_limiter", main.SimpleRateLimiter(limit_per_window=100, window_seconds=60, enabled=False))

    with TestClient(main.app) as client:
        response = client.get("/health")

    assert response.status_code == 200


def test_security_gate_dashboard_requires_auth_by_default(monkeypatch):
    from backend.api import main

    monkeypatch.setenv("DEV_MODE", "0")
    _set_required_production_env(monkeypatch)
    monkeypatch.setenv("API_AUTH_KEYS", "release-key-1")
    monkeypatch.delenv("API_PUBLIC_PATHS", raising=False)
    monkeypatch.setattr(main, "_rate_limiter", main.SimpleRateLimiter(limit_per_window=100, window_seconds=60, enabled=False))

    with TestClient(main.app) as client:
        response = client.get("/api/dashboard", params={"symbol": "AAPL"})

    assert response.status_code == 401
    assert response.json().get("detail") == "Unauthorized"


def test_allowlisted_paths_can_be_configured_via_env(monkeypatch):
    from backend.api import main

    monkeypatch.delenv("API_PUBLIC_PATHS", raising=False)
    assert main._is_allowlisted_path("/api/dashboard") is False

    monkeypatch.setenv("API_PUBLIC_PATHS", "/health,/api/dashboard")
    assert main._is_allowlisted_path("/api/dashboard") is True
    assert main._is_allowlisted_path("/api/dashboard/sub") is False


def test_security_gate_rate_limit_blocks_second_request(monkeypatch):
    from backend.api import main

    monkeypatch.setenv("DEV_MODE", "0")
    _set_required_production_env(monkeypatch)
    monkeypatch.setenv("API_AUTH_KEYS", "release-key-1")
    monkeypatch.setattr(main, "_rate_limiter", main.SimpleRateLimiter(limit_per_window=1, window_seconds=60, enabled=True))

    with TestClient(main.app) as client:
        first = client.get("/api/user/profile", headers={"x-api-key": "release-key-1"})
        second = client.get("/api/user/profile", headers={"x-api-key": "release-key-1"})

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json().get("detail") == "Rate limit exceeded"
    assert second.headers.get("Retry-After") is not None
