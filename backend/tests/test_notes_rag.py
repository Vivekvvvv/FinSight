# -*- coding: utf-8 -*-
"""
tests/test_notes_rag.py
单元测试：研究笔记 RAG 向量化与语义搜索
"""
import json
import math
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── _cosine 测试 ──────────────────────────────────────────────────────────────

def test_cosine_identical_vectors():
    from backend.services.notes_rag import _cosine
    v = [1.0, 2.0, 3.0]
    assert abs(_cosine(v, v) - 1.0) < 1e-9


def test_cosine_orthogonal_vectors():
    from backend.services.notes_rag import _cosine
    a = [1.0, 0.0, 0.0]
    b = [0.0, 1.0, 0.0]
    assert abs(_cosine(a, b)) < 1e-9


def test_cosine_zero_vector_returns_zero():
    from backend.services.notes_rag import _cosine
    assert _cosine([0.0, 0.0], [1.0, 2.0]) == 0.0


def test_cosine_mismatched_dimensions_return_zero():
    from backend.services.notes_rag import _cosine

    assert _cosine([1.0], [1.0, 2.0]) == 0.0
    assert _cosine([], []) == 0.0


def test_cosine_opposite_vectors():
    from backend.services.notes_rag import _cosine
    v = [1.0, 2.0]
    neg = [-1.0, -2.0]
    assert abs(_cosine(v, neg) - (-1.0)) < 1e-9


# ── vectorize_note 测试 ────────────────────────────────────────────────────────

def test_vectorize_note_returns_false_when_embedder_unavailable():
    """EmbeddingService 不可用时应静默返回 False，不抛异常"""
    with patch("backend.services.notes_rag._embed", return_value=None):
        from backend.services.notes_rag import vectorize_note
        result = vectorize_note("note_001", "标题", "内容")
    assert result is False


def test_vectorize_note_returns_true_when_embedder_available(tmp_path):
    """EmbeddingService 可用时应写入 SQLite 并返回 True"""
    import backend.services.notes_rag as rag_module
    fake_vec = [0.1, 0.2, 0.3]

    with patch.object(rag_module, "_DB_PATH", tmp_path / "test_notes.db"), \
         patch.object(rag_module, "_table_ready", False), \
         patch("backend.services.notes_rag._embed", return_value=fake_vec):
        result = rag_module.vectorize_note("note_x", "测试标题", "测试内容")

    assert result is True


def test_vectorize_note_write_error_log_is_redacted(monkeypatch, caplog):
    import backend.services.notes_rag as rag_module

    secret = "PRIVATE postgres://notes:secret@db/vector"

    def _fail_conn():
        raise RuntimeError(secret)

    monkeypatch.setattr(rag_module, "_init", lambda: None)
    monkeypatch.setattr(rag_module, "_embed", lambda _text: [0.1])
    monkeypatch.setattr(rag_module, "_conn", _fail_conn)

    assert rag_module.vectorize_note("note-private", "title", "content") is False
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_notes_embedding_error_log_is_redacted(monkeypatch, caplog):
    import backend.services.notes_rag as rag_module

    secret = "PRIVATE postgres://notes:secret@db/embed"

    class _FailingEmbedder:
        def embed_texts(self, _texts):
            raise RuntimeError(secret)

    caplog.set_level("DEBUG")
    monkeypatch.setattr(rag_module, "_get_embedder", lambda: _FailingEmbedder())

    assert rag_module._embed("private note") is None
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


# ── semantic_search_notes fallback 测试 ──────────────────────────────────────

@pytest.mark.parametrize("vector", [[float("nan")], [float("inf")], ["bad"]])
def test_embed_rejects_invalid_vectors(monkeypatch, vector):
    import backend.services.notes_rag as rag_module

    embedder = MagicMock()
    embedder.embed_texts.return_value.dense = [vector]
    monkeypatch.setattr(rag_module, "_get_embedder", lambda: embedder)

    assert rag_module._embed("text") is None


def test_semantic_search_falls_back_to_keyword_when_no_embedder():
    """embed 返回 None 时应调用关键词搜索作为降级"""
    keyword_results = [{"note_id": "1", "title": "关键词命中"}]

    with patch("backend.services.notes_rag._embed", return_value=None), \
         patch("backend.services.research_notes.search_notes", return_value=keyword_results) as mock_kw:
        from backend.services.notes_rag import semantic_search_notes
        result = semantic_search_notes("sid", "uid", "关键词查询", limit=5)

    assert result == keyword_results


def test_vector_search_sanitizes_corrupt_vector_and_tags(monkeypatch, caplog):
    import backend.services.notes_rag as rag_module

    row = (
        "note-1",
        "[NaN]",
        "title",
        "content",
        "AAPL",
        "{bad-json",
        "2026-01-01",
        "2026-01-01",
    )
    connection = MagicMock()
    connection.execute.return_value.fetchall.return_value = [row]
    context = MagicMock()
    context.__enter__.return_value = connection
    context.__exit__.return_value = False
    monkeypatch.setattr(rag_module, "_conn", lambda: context)

    result = rag_module._vector_search("sid", "uid", [1.0], 10)

    assert result[0]["similarity"] == 0.0
    assert result[0]["tags"] == []
    assert "invalid stored note vector (ValueError)" in caplog.text
    assert "invalid stored note tags (JSONDecodeError)" in caplog.text


def test_vector_search_rejects_non_finite_tags(monkeypatch, caplog):
    import backend.services.notes_rag as rag_module

    row = (
        "note-1",
        "[1.0]",
        "title",
        "content",
        "AAPL",
        "[NaN]",
        "2026-01-01",
        "2026-01-01",
    )
    connection = MagicMock()
    connection.execute.return_value.fetchall.return_value = [row]
    context = MagicMock()
    context.__enter__.return_value = connection
    context.__exit__.return_value = False
    monkeypatch.setattr(rag_module, "_conn", lambda: context)

    result = rag_module._vector_search("sid", "uid", [1.0], 10)

    assert result[0]["tags"] == []
    assert "invalid stored note tags (ValueError)" in caplog.text


# ── vectorize_all_notes 测试 ──────────────────────────────────────────────────

def test_vectorize_all_notes_returns_stats_dict():
    """返回值必须包含 vectorized/failed/total 三个键"""
    with patch("backend.services.notes_rag._embed", return_value=None):
        # 没有可向量化的笔记时，返回全 0
        import backend.services.notes_rag as rag_module
        with patch.object(rag_module, "_conn") as mock_conn:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []
            mock_conn.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_conn.return_value.__exit__ = MagicMock(return_value=False)
            mock_cursor.execute.return_value = mock_cursor

            result = rag_module.vectorize_all_notes("sid", "uid")

    assert "vectorized" in result
    assert "failed" in result
    assert "total" in result
