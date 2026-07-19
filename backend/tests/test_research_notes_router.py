# -*- coding: utf-8 -*-
"""Research Notes 路由层回归测试。

覆盖三类历史 bug：
1. GET /api/research-notes/semantic-search 被 /{note_id} 路由遮蔽（永远 404）
2. semantic-search 内 require_matching_identity 位置传参（keyword-only，必 TypeError）
3. notes_rag 与 research_notes 指向不同 SQLite 文件（跨表 JOIN 报 no such table）
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.security.auth import Principal, get_current_user
from backend.services import research_notes


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def authenticated_client():
    principal = Principal(
        user_id="pytest_authenticated_user",
        email="notes@example.invalid",
        role="user",
        auth_type="api_key",
    )
    app.dependency_overrides[get_current_user] = lambda: principal
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_semantic_search_not_shadowed_by_note_id_route(client):
    """semantic-search 必须命中专用路由，而不是被 /{note_id} 当作笔记 ID 返回 404。"""
    resp = client.get(
        "/api/research-notes/semantic-search",
        params={"session_id": "pytest_router_session", "user_id": "default_user", "q": "估值"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "估值"
    assert isinstance(data["results"], list)
    assert data["total"] == len(data["results"])


def test_get_note_by_id_still_returns_404_for_missing(client):
    """路由顺序调整后，/{note_id} 语义不变。"""
    resp = client.get("/api/research-notes/note_doesnotexist99")
    assert resp.status_code == 404


def test_vectorize_all_reachable_and_returns_stats(client):
    """向量库与笔记库同文件后，vectorize-all 的跨表 JOIN 不再报 no such table。"""
    resp = client.post(
        "/api/research-notes/vectorize-all",
        params={"session_id": "pytest_router_session", "user_id": "default_user"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert {"vectorized", "failed", "total"} <= set(data.keys())


def test_notes_rag_and_research_notes_share_db_file():
    """notes_rag 的向量表必须和 research_notes 的笔记表在同一个 SQLite 文件里。"""
    from backend.services import notes_rag, research_notes

    assert notes_rag._DB_PATH.resolve() == research_notes._DB_PATH.resolve()


def test_create_default_user_uses_authenticated_principal(authenticated_client, monkeypatch):
    captured = {}

    def fake_create_note(**kwargs):
        captured.update(kwargs)
        return "note_scoped_to_principal"

    monkeypatch.setattr(research_notes, "create_note", fake_create_note)

    response = authenticated_client.post(
        "/api/research-notes",
        json={"session_id": "pytest_router_session", "title": "隔离测试"},
    )

    assert response.status_code == 200
    assert captured["user_id"] == "pytest_authenticated_user"


def test_list_default_user_uses_authenticated_principal(authenticated_client, monkeypatch):
    captured = {}

    def fake_list_notes(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(research_notes, "list_notes", fake_list_notes)

    response = authenticated_client.get(
        "/api/research-notes",
        params={"session_id": "pytest_router_session"},
    )

    assert response.status_code == 200
    assert captured["user_id"] == "pytest_authenticated_user"


def test_semantic_search_default_user_uses_authenticated_principal(authenticated_client, monkeypatch):
    from backend.services import notes_rag

    captured = {}

    def fake_semantic_search_notes(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(notes_rag, "semantic_search_notes", fake_semantic_search_notes)

    response = authenticated_client.get(
        "/api/research-notes/semantic-search",
        params={"session_id": "pytest_router_session", "q": "隔离测试"},
    )

    assert response.status_code == 200
    assert captured["user_id"] == "pytest_authenticated_user"


def test_vectorize_default_user_uses_authenticated_principal(authenticated_client, monkeypatch):
    from backend.services import notes_rag

    captured = {}

    def fake_vectorize_all_notes(**kwargs):
        captured.update(kwargs)
        return {"vectorized": 0, "failed": 0, "total": 0}

    monkeypatch.setattr(notes_rag, "vectorize_all_notes", fake_vectorize_all_notes)

    response = authenticated_client.post(
        "/api/research-notes/vectorize-all",
        params={"session_id": "pytest_router_session", "user_id": "default_user"},
    )

    assert response.status_code == 200
    assert captured["user_id"] == "pytest_authenticated_user"
