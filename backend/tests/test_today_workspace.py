# -*- coding: utf-8 -*-
"""今日工作台的新鲜度契约：没有实时行情就不能对外标 live。"""
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.api.main import app


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
