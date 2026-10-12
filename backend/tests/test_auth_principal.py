from __future__ import annotations

from fastapi.testclient import TestClient


def test_secure_secret_in_checks_every_candidate(monkeypatch):
    from backend.security import auth

    calls = []

    def compare(candidate, expected):
        calls.append((candidate, expected))
        return candidate == expected

    monkeypatch.setattr(auth, "secure_secret_matches", compare)

    assert auth.secure_secret_in("match", ["match", "other"]) is True
    assert calls == [("match", "match"), ("match", "other")]


def test_secure_secret_matches_supports_unicode_values():
    from backend.security.auth import secure_secret_matches

    assert secure_secret_matches("密钥", "密钥") is True
    assert secure_secret_matches("密钥", "其他") is False


def _set_prod_env(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "0")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_BASE", "https://llm.test/v1")
    monkeypatch.setenv("OPENAI_COMPATIBLE_MODEL", "test-model")
    monkeypatch.setenv("POSTGRES_DB", "test")
    monkeypatch.setenv("POSTGRES_USER", "test")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test")
    monkeypatch.setenv("JWT_SECRET", "0123456789abcdef0123456789abcdef")
    monkeypatch.setenv("API_AUTH_KEYS", "release-key-1")
    monkeypatch.setenv("API_AUTH_PRINCIPALS", '{"release-key-1":{"user_id":"alice","email":"alice@example.invalid","role":"user"}}')


def test_principal_user_id_stays_storage_safe(monkeypatch):
    """配置里越界的 user_id 必须落回派生 id。

    user_id 会成为 memory 存储键与 session_id 的中间分段，两处都只接受
    [A-Za-z0-9._-]{1,64}；放行邮箱这类值会让该主体的会话端点全线 422/500，
    而 /api/me 下发的正是这个值、require_matching_identity 又不许前端换。
    """
    from backend.security.auth import api_key_fingerprint, principal_from_api_key

    monkeypatch.setenv("API_AUTH_KEYS", "release-key-1")
    monkeypatch.delenv("API_AUTH_PRINCIPALS", raising=False)
    derived = api_key_fingerprint("release-key-1")

    monkeypatch.setenv("API_AUTH_DEFAULT_USER_ID", "ops.team-1")
    assert principal_from_api_key("release-key-1").user_id == "ops.team-1"

    for bad in ("analyst@corp.com", "tenant:alice", "has space", "a" * 65, "../etc/passwd"):
        monkeypatch.setenv("API_AUTH_DEFAULT_USER_ID", bad)
        principal = principal_from_api_key("release-key-1")
        assert principal.user_id == derived
        assert principal.session_id == f"private:{derived}:default"

    monkeypatch.setenv(
        "API_AUTH_PRINCIPALS",
        '{"release-key-1":{"user_id":"alice@example.invalid","role":"user"}}',
    )
    assert principal_from_api_key("release-key-1").user_id == derived


def test_user_route_rejects_forged_user_id(monkeypatch):
    from backend.api import main

    _set_prod_env(monkeypatch)
    monkeypatch.setattr(main, "_rate_limiter", main.SimpleRateLimiter(limit_per_window=100, window_seconds=60, enabled=False))

    with TestClient(main.app) as client:
        response = client.get(
            "/api/user/profile",
            params={"user_id": "bob"},
            headers={"x-api-key": "release-key-1"},
        )

    assert response.status_code == 403


def test_portfolio_route_rejects_forged_session_id(monkeypatch):
    from backend.api import main

    _set_prod_env(monkeypatch)
    monkeypatch.setattr(main, "_rate_limiter", main.SimpleRateLimiter(limit_per_window=100, window_seconds=60, enabled=False))

    with TestClient(main.app) as client:
        response = client.get(
            "/api/portfolio/summary",
            params={"session_id": "private:bob:default"},
            headers={"x-api-key": "release-key-1"},
        )

    assert response.status_code == 403


def test_subscription_route_rejects_forged_email(monkeypatch):
    from backend.api import main

    _set_prod_env(monkeypatch)
    monkeypatch.setattr(main, "_rate_limiter", main.SimpleRateLimiter(limit_per_window=100, window_seconds=60, enabled=False))

    with TestClient(main.app) as client:
        response = client.get(
            "/api/subscriptions",
            params={"email": "bob@example.invalid"},
            headers={"x-api-key": "release-key-1"},
        )

    assert response.status_code == 403
