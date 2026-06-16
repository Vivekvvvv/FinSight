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


# ── semantic_search_notes fallback 测试 ──────────────────────────────────────

def test_semantic_search_falls_back_to_keyword_when_no_embedder():
    """embed 返回 None 时应调用关键词搜索作为降级"""
    keyword_results = [{"note_id": "1", "title": "关键词命中"}]

    with patch("backend.services.notes_rag._embed", return_value=None), \
         patch("backend.services.research_notes.search_notes", return_value=keyword_results) as mock_kw:
        from backend.services.notes_rag import semantic_search_notes
        result = semantic_search_notes("sid", "uid", "关键词查询", limit=5)

    assert result == keyword_results


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
