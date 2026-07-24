# -*- coding: utf-8 -*-
"""F 类回归（docs/BUG_AUDIT_2026-07-04.md）：路由层内部异常不得压成 200。

历史行为：today / research-notes 的宽 except 返回 200 + {"success": False}
（today 还带整套空骨架），前端把它当正常数据渲染，后端故障对用户与监控
完全不可见。修复后统一 raise HTTPException(500)，与同文件 semantic-search /
vectorize 端点的既有语义一致。
"""
from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_today_internal_error_is_redacted(client, monkeypatch, caplog):
    from backend.api import today_router as module

    def _boom():
        raise RuntimeError("private today workspace detail")

    monkeypatch.setattr(module, "is_demo_mode", _boom)
    caplog.set_level(logging.ERROR, logger="backend.api.today_router")
    response = client.get("/api/today", params={"session_id": "pytest_router_session"})

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"
    assert "private today workspace detail" not in response.text
    assert "private today workspace detail" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_notes_list_internal_error_returns_500(client, monkeypatch):
    from backend.services import research_notes as notes_service

    def _boom(**_kwargs):
        raise RuntimeError("notes db exploded")

    monkeypatch.setattr(notes_service, "list_notes", _boom)
    resp = client.get(
        "/api/research-notes",
        params={"session_id": "pytest_router_session", "user_id": "default_user"},
    )
    assert resp.status_code == 500


def test_notes_create_internal_error_returns_500(client, monkeypatch):
    from backend.services import research_notes as notes_service

    def _boom(**_kwargs):
        raise RuntimeError("notes db exploded")

    monkeypatch.setattr(notes_service, "create_note", _boom)
    resp = client.post(
        "/api/research-notes",
        json={
            "session_id": "pytest_router_session",
            "user_id": "default_user",
            "title": "t",
            "content": "c",
        },
    )
    assert resp.status_code == 500


def test_notes_missing_still_404_not_500(client):
    """既有 404 语义不受影响：不存在的笔记仍返回 404。"""
    resp = client.get("/api/research-notes/note_doesnotexist99")
    assert resp.status_code == 404


def test_timeline_invalid_event_type_returns_400_not_500(client):
    """R13 回归：try 内抛出的 HTTPException(400) 不得被宽 except 重包成 500。"""
    resp = client.get(
        "/api/timeline/AAPL",
        params={"session_id": "pytest_router_session", "event_type": "bogus"},
    )
    assert resp.status_code == 400
