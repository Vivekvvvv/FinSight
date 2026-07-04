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


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


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
