# -*- coding: utf-8 -*-
"""Research Notes 路由层回归测试。

覆盖三类历史 bug：
1. GET /api/research-notes/semantic-search 被 /{note_id} 路由遮蔽（永远 404）
2. semantic-search 内 require_matching_identity 位置传参（keyword-only，必 TypeError）
3. notes_rag 与 research_notes 指向不同 SQLite 文件（跨表 JOIN 报 no such table）
"""
from __future__ import annotations

import logging

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


@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        (
            "post",
            "/api/research-notes",
            {"json": {"session_id": "pytest_router_session", "title": "Note", "content": "x" * 100_001}},
        ),
        (
            "post",
            "/api/research-notes",
            {"json": {"session_id": "pytest_router_session", "title": "Note", "tags": ["tag"] * 21}},
        ),
        (
            "post",
            "/api/research-notes",
            {"json": {"session_id": "pytest_router_session", "title": "Note", "tags": ["x" * 65]}},
        ),
        (
            "put",
            "/api/research-notes/note-1",
            {"json": {"title": "x" * 513}},
        ),
        (
            "put",
            "/api/research-notes/note-1",
            {"json": {"tags": ["x" * 65]}},
        ),
        (
            "get",
            "/api/research-notes/semantic-search",
            {"params": {"session_id": "pytest_router_session", "q": "note", "limit": 0}},
        ),
        (
            "get",
            "/api/research-notes",
            {"params": {"session_id": "pytest_router_session", "q": "x" * 2049}},
        ),
    ],
)
def test_research_notes_reject_oversized_or_invalid_inputs(authenticated_client, method, path, kwargs):
    response = getattr(authenticated_client, method)(path, **kwargs)

    assert response.status_code == 422


def test_research_notes_rejects_oversized_note_id_before_store(
    authenticated_client,
    monkeypatch,
):
    calls: list[str] = []
    monkeypatch.setattr(
        research_notes,
        "get_note",
        lambda note_id: calls.append(note_id),
    )

    response = authenticated_client.get(f"/api/research-notes/{'n' * 129}")

    assert response.status_code == 422
    assert calls == []


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


def _assert_internal_error_redacted(response, caplog, secret: str) -> None:
    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"
    assert secret not in response.text
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_create_note_internal_error_is_redacted(authenticated_client, monkeypatch, caplog):
    secret = "C:/private/notes.db create detail"

    def fail_create_note(*_args, **_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(research_notes, "create_note", fail_create_note)
    caplog.set_level(logging.ERROR, logger="backend.api.research_notes_router")

    response = authenticated_client.post(
        "/api/research-notes",
        json={"session_id": "pytest_router_session", "title": "private research"},
    )
    _assert_internal_error_redacted(response, caplog, secret)


def test_list_notes_internal_error_is_redacted(authenticated_client, monkeypatch, caplog):
    secret = "C:/private/notes.db list detail"

    def fail_list_notes(*_args, **_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(research_notes, "list_notes", fail_list_notes)
    caplog.set_level(logging.ERROR, logger="backend.api.research_notes_router")

    response = authenticated_client.get(
        "/api/research-notes",
        params={"session_id": "pytest_router_session"},
    )
    _assert_internal_error_redacted(response, caplog, secret)


def test_semantic_search_internal_error_is_redacted(authenticated_client, monkeypatch, caplog):
    from backend.services import notes_rag

    secret = "C:/private/vector.db search detail"

    def fail_semantic_search_notes(*_args, **_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(notes_rag, "semantic_search_notes", fail_semantic_search_notes)
    caplog.set_level(logging.ERROR, logger="backend.api.research_notes_router")

    response = authenticated_client.get(
        "/api/research-notes/semantic-search",
        params={"session_id": "pytest_router_session", "q": "估值"},
    )
    _assert_internal_error_redacted(response, caplog, secret)


def test_get_note_internal_error_is_redacted(authenticated_client, monkeypatch, caplog):
    secret = "C:/private/notes.db get detail"

    def fail_get_note(_note_id):
        raise RuntimeError(secret)

    monkeypatch.setattr(research_notes, "get_note", fail_get_note)
    caplog.set_level(logging.ERROR, logger="backend.api.research_notes_router")

    response = authenticated_client.get("/api/research-notes/note-1")
    _assert_internal_error_redacted(response, caplog, secret)


def test_update_note_internal_error_is_redacted(authenticated_client, monkeypatch, caplog):
    secret = "C:/private/notes.db update detail"

    monkeypatch.setattr(
        research_notes,
        "get_note",
        lambda _note_id: {"user_id": "pytest_authenticated_user"},
    )

    def fail_update_note(*_args, **_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(research_notes, "update_note", fail_update_note)
    caplog.set_level(logging.ERROR, logger="backend.api.research_notes_router")

    response = authenticated_client.put(
        "/api/research-notes/note-1",
        json={"title": "updated"},
    )
    _assert_internal_error_redacted(response, caplog, secret)


def test_delete_note_internal_error_is_redacted(authenticated_client, monkeypatch, caplog):
    secret = "C:/private/notes.db delete detail"

    monkeypatch.setattr(
        research_notes,
        "get_note",
        lambda _note_id: {"user_id": "pytest_authenticated_user"},
    )

    def fail_delete_note(*_args, **_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(research_notes, "delete_note", fail_delete_note)
    caplog.set_level(logging.ERROR, logger="backend.api.research_notes_router")

    response = authenticated_client.delete("/api/research-notes/note-1")
    _assert_internal_error_redacted(response, caplog, secret)


def test_upload_note_image_internal_error_is_redacted(authenticated_client, monkeypatch, caplog):
    from backend.services import note_images

    secret = "C:/private/uploads/storage detail"

    async def fail_save_image(*_args, **_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(
        research_notes,
        "get_note",
        lambda _note_id: {"user_id": "pytest_authenticated_user"},
    )
    monkeypatch.setattr(note_images, "save_image", fail_save_image)
    caplog.set_level(logging.ERROR, logger="backend.api.research_notes_router")

    response = authenticated_client.post(
        "/api/research-notes/note-1/images",
        files={"file": ("chart.png", b"image-bytes", "image/png")},
    )
    _assert_internal_error_redacted(response, caplog, secret)


def test_get_note_image_internal_error_is_redacted(authenticated_client, monkeypatch, caplog):
    from backend.services import note_images

    secret = "C:/private/uploads/read detail"

    def fail_get_image_path(*_args, **_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(note_images, "get_image_path", fail_get_image_path)
    caplog.set_level(logging.ERROR, logger="backend.api.research_notes_router")

    response = authenticated_client.get(
        "/api/notes/images/pytest_authenticated_user/note-1/chart.png",
    )
    _assert_internal_error_redacted(response, caplog, secret)


def test_get_note_image_sets_exact_media_type_and_nosniff(authenticated_client, monkeypatch, tmp_path):
    from backend.services import note_images

    image_path = tmp_path / "chart.jpg"
    image_path.write_bytes(b"\xff\xd8\xff\xe0test-image")
    monkeypatch.setattr(note_images, "get_image_path", lambda *_args, **_kwargs: image_path)

    response = authenticated_client.get(
        "/api/notes/images/pytest_authenticated_user/note-1/chart.jpg",
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_list_note_images_internal_error_is_redacted(authenticated_client, monkeypatch, caplog):
    from backend.services import note_images

    secret = "C:/private/uploads/list detail"

    monkeypatch.setattr(
        research_notes,
        "get_note",
        lambda _note_id: {"user_id": "pytest_authenticated_user"},
    )

    def fail_list_images(*_args, **_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(note_images, "list_images", fail_list_images)
    caplog.set_level(logging.ERROR, logger="backend.api.research_notes_router")

    response = authenticated_client.get("/api/research-notes/note-1/images")
    _assert_internal_error_redacted(response, caplog, secret)


def test_delete_note_image_internal_error_is_redacted(authenticated_client, monkeypatch, caplog):
    from backend.services import note_images

    secret = "C:/private/uploads/delete detail"

    monkeypatch.setattr(
        research_notes,
        "get_note",
        lambda _note_id: {"user_id": "pytest_authenticated_user"},
    )

    def fail_delete_image(*_args, **_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(note_images, "delete_image", fail_delete_image)
    caplog.set_level(logging.ERROR, logger="backend.api.research_notes_router")

    response = authenticated_client.delete("/api/research-notes/note-1/images/chart.png")
    _assert_internal_error_redacted(response, caplog, secret)


def test_vectorize_all_internal_error_is_redacted(authenticated_client, monkeypatch, caplog):
    from backend.services import notes_rag

    secret = "C:/private/vector.db vectorize detail"

    def fail_vectorize_all_notes(*_args, **_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(notes_rag, "vectorize_all_notes", fail_vectorize_all_notes)
    caplog.set_level(logging.ERROR, logger="backend.api.research_notes_router")

    response = authenticated_client.post(
        "/api/research-notes/vectorize-all",
        params={"session_id": "pytest_router_session", "user_id": "default_user"},
    )
    _assert_internal_error_redacted(response, caplog, secret)
