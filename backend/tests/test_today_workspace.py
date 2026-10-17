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


def test_today_workspace_surfaces_alert_feed_failure(monkeypatch):
    monkeypatch.delenv("FINSIGHT_DEMO_MODE", raising=False)
    principal = Principal(user_id="today-alert-user", role="user", auth_type="api_key")
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
