# -*- coding: utf-8 -*-
"""Tests for backend.rag.reranker — RerankerService with fallback."""
from __future__ import annotations

import builtins
import logging

from backend.rag.reranker import RerankerService


def test_reranker_disabled_returns_original_order():
    """When reranker is disabled, documents are returned in original order."""
    svc = RerankerService(force_backend="none")
    assert not svc.is_enabled

    docs = [
        {"content": "Apple revenue guidance", "source_id": "a"},
        {"content": "Microsoft Azure growth", "source_id": "b"},
        {"content": "Tesla delivery numbers", "source_id": "c"},
    ]
    result = svc.rerank("Apple earnings", docs, top_n=2)
    assert len(result) == 2
    assert result[0]["source_id"] == "a"
    assert result[1]["source_id"] == "b"


def test_reranker_disabled_empty_query():
    svc = RerankerService(force_backend="none")
    docs = [{"content": "test", "source_id": "x"}]
    result = svc.rerank("", docs, top_n=5)
    assert len(result) == 1


def test_reranker_disabled_empty_docs():
    svc = RerankerService(force_backend="none")
    result = svc.rerank("test query", [], top_n=5)
    assert result == []


def test_reranker_top_n_clipping():
    """Top-N should limit the output."""
    svc = RerankerService(force_backend="none")
    docs = [{"content": f"doc {i}", "source_id": str(i)} for i in range(10)]
    result = svc.rerank("query", docs, top_n=3)
    assert len(result) == 3


def test_reranker_import_error_log_is_redacted(monkeypatch, caplog):
    import backend.rag.reranker as reranker

    sentinel = "PRIVATE_RERANKER_MODEL_PATH"
    real_import = builtins.__import__

    def _import(name, *args, **kwargs):
        if name == "sentence_transformers":
            raise ImportError(sentinel)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _import)
    caplog.set_level(logging.INFO, logger=reranker.__name__)

    svc = reranker.RerankerService(force_backend="bge-reranker")

    assert not svc.is_enabled
    assert sentinel not in caplog.text
    assert "ImportError" in caplog.text


def test_reranker_inference_error_log_is_redacted(monkeypatch, caplog):
    import backend.rag.reranker as reranker

    sentinel = "PRIVATE_RERANKER_RUNTIME_DETAIL"
    docs = [{"content": "first", "source_id": "a"}, {"content": "second", "source_id": "b"}]

    class _BoomReranker:
        def predict(self, _pairs):
            raise RuntimeError(sentinel)

    svc = reranker.RerankerService(force_backend="bge-reranker")
    monkeypatch.setattr(svc, "_check_available", lambda: True)
    monkeypatch.setattr(reranker, "_get_reranker", lambda: _BoomReranker())
    caplog.set_level(logging.INFO, logger=reranker.__name__)

    result = svc.rerank("query", docs, top_n=2)

    assert result == docs
    assert sentinel not in caplog.text
    assert "RuntimeError" in caplog.text
