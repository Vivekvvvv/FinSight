# -*- coding: utf-8 -*-
"""R33 回归：CORS 中间件必须在 security_gate 外层。

Starlette 后注册者在最外层。此前 CORS 先注册（内层）：生产模式下浏览器
预检 OPTIONS 不带鉴权头，被 security_gate 直接 401 且响应不经过 CORS
中间件（无 Access-Control-* 头）——跨域部署的前端完全无法调用后端，
所有真实鉴权错误都被浏览器显示成 CORS 错误。
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


def test_preflight_options_answered_by_cors_not_401(monkeypatch):
    from backend.api import main

    _set_prod_env(monkeypatch)
    monkeypatch.setattr(
        main, "_rate_limiter",
        main.SimpleRateLimiter(limit_per_window=100, window_seconds=60, enabled=False),
    )
    with TestClient(main.app) as client:
        resp = client.options(
            "/api/today",
            headers={
                "Origin": "http://localhost:5173",  # 默认白名单来源
                "Access-Control-Request-Method": "GET",
            },
        )
    assert resp.status_code == 200  # 旧代码：security_gate 先执行 → 401
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_auth_error_response_carries_cors_headers(monkeypatch):
    """401 等鉴权错误响应也要经过外层 CORS 补头，浏览器才能读到真实状态码。"""
    from backend.api import main

    _set_prod_env(monkeypatch)
    monkeypatch.setattr(
        main, "_rate_limiter",
        main.SimpleRateLimiter(limit_per_window=100, window_seconds=60, enabled=False),
    )
    with TestClient(main.app) as client:
        resp = client.get(
            "/api/today",
            params={"session_id": "s"},
            headers={"Origin": "http://localhost:5173"},  # 无鉴权头 → 401
        )
    assert resp.status_code == 401
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
