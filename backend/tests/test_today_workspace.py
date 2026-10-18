# -*- coding: utf-8 -*-
"""今日工作台的新鲜度契约：没有实时行情就不能对外标 live。"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api.today_router import TodayRouterDeps, create_today_router
from backend.security.auth import Principal, get_current_user


class _Memory:
    def list_watchlist_items(self, _user_id):
        return []


class _BrokenSubscriptions:
    def list_alert_events(self, *_args, **_kwargs):
        raise RuntimeError("subscription store is down")


class _RecordingSubscriptions:
    def __init__(self):
        self.emails = []

    def list_alert_events(self, email, limit=10):
        self.emails.append(email)
        return []


def _today_client(principal, subscription_service):
    test_app = FastAPI()
    test_app.include_router(
        create_today_router(
            TodayRouterDeps(
                resolve_thread_id=lambda session_id: session_id,
                memory_service=_Memory(),
                subscription_service=subscription_service,
            )
        )
    )
    test_app.dependency_overrides[get_current_user] = lambda: principal
    return TestClient(test_app)


def test_today_workspace_surfaces_alert_feed_failure(monkeypatch):
    monkeypatch.delenv("FINSIGHT_DEMO_MODE", raising=False)
    principal = Principal(
        user_id="today-alert-user",
        email="today-alert-user@example.com",
        role="user",
        auth_type="api_key",
    )
    test_app = FastAPI()
    test_app.include_router(
        create_today_router(
            TodayRouterDeps(
                resolve_thread_id=lambda session_id: session_id,
                memory_service=_Memory(),
                subscription_service=_BrokenSubscriptions(),
            )
        )
    )
    test_app.dependency_overrides[get_current_user] = lambda: principal

    with TestClient(test_app) as client:
        response = client.get(
            "/api/today",
            params={"session_id": principal.session_id},
        )

    assert response.status_code == 200
    payload = response.json()
    # 告警读取失败不能伪装成“没有告警”
    assert payload["alert_feed"] == []
    assert payload["alert_feed_unavailable"] is True
    assert payload["degraded"] is True


def test_today_workspace_queries_alerts_by_principal_email(monkeypatch):
    monkeypatch.delenv("FINSIGHT_DEMO_MODE", raising=False)
    # JWT 用户的 user_id 是 UUID 而非邮箱：必须用认证主体的 email 查订阅，
    # 拿 user_id 拼出来的假邮箱永远查不到订阅。
    principal = Principal(
        user_id="3f2a-uuid-not-email",
        email="alice@example.com",
        role="user",
        auth_type="jwt",
    )
    service = _RecordingSubscriptions()

    with _today_client(principal, service) as client:
        response = client.get("/api/today", params={"session_id": principal.session_id})

    assert response.status_code == 200
    assert service.emails == ["alice@example.com"]


def test_today_workspace_without_email_does_not_query_fake_address(monkeypatch):
    monkeypatch.delenv("FINSIGHT_DEMO_MODE", raising=False)
    principal = Principal(user_id="guest:anonymous", role="guest", auth_type="anonymous")
    service = _RecordingSubscriptions()

    with _today_client(principal, service) as client:
        response = client.get("/api/today", params={"session_id": principal.session_id})

    assert response.status_code == 200
    payload = response.json()
    # 没有邮箱就没有可查的订阅键，但不该当成“服务故障”，也不该拿假地址去查。
    assert service.emails == []
    assert payload["alert_feed"] == []
    assert payload["alert_feed_unavailable"] is False


def test_today_workspace_marks_cached_without_live_quotes(monkeypatch):
    monkeypatch.delenv("FINSIGHT_DEMO_MODE", raising=False)

    with TestClient(app) as client:
        response = client.get("/api/today", params={"session_id": "pytest_router_session"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    # 该接口只读本地存储：总市值为 None、自选动态恒为空，没有实时报价。
    assert payload["freshness_status"] == "cached"
    assert payload["freshness_status"] != "live"
    assert payload["portfolio_snapshot"]["total_value"] is None
    assert payload["watchlist_movers"] == []
