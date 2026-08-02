import logging

import pytest

from backend.rag import observability_store as observability


def _install_test_hooks(monkeypatch, *, ingest, search, store):
    monkeypatch.setattr(observability.HybridRAGService, "ingest_documents", ingest)
    monkeypatch.setattr(observability.HybridRAGService, "hybrid_search", search)
    monkeypatch.setattr(
        observability.HybridRAGService,
        "_rag_observability_hooks_installed",
        False,
        raising=False,
    )
    monkeypatch.setattr(observability, "_hooks_installed", False)
    monkeypatch.setattr(observability, "get_rag_observability_store", lambda: store)
    assert observability.install_rag_observability_hooks() is True


def test_ingest_observability_error_log_is_redacted(monkeypatch, caplog):
    class FailingStore:
        @staticmethod
        def cache_ingest_batch(**_kwargs):
            raise RuntimeError("private ingest observability detail")

    def ingest(_self, docs):
        return {"count": len(docs)}

    def search(_self, _query, *, collection, top_k=6):
        return []

    _install_test_hooks(
        monkeypatch,
        ingest=ingest,
        search=search,
        store=FailingStore(),
    )
    service = observability.HybridRAGService.__new__(observability.HybridRAGService)
    service.backend_name = "memory"

    with caplog.at_level(logging.ERROR, logger="backend.rag.observability_store"):
        result = service.ingest_documents([object()])

    assert result == {"count": 1}
    assert "private ingest observability detail" not in caplog.text
    assert "[RAGObservability]" in caplog.text


def test_search_run_creation_error_log_is_redacted(monkeypatch, caplog):
    class FailingStore:
        @staticmethod
        def begin_search_run(**_kwargs):
            raise RuntimeError("private search run creation detail")

    def ingest(_self, docs):
        return {"count": len(docs)}

    def search(_self, query, *, collection, top_k=6):
        return [{"query": query, "collection": collection, "top_k": top_k}]

    _install_test_hooks(
        monkeypatch,
        ingest=ingest,
        search=search,
        store=FailingStore(),
    )
    service = observability.HybridRAGService.__new__(observability.HybridRAGService)
    service.backend_name = "memory"

    with caplog.at_level(logging.ERROR, logger="backend.rag.observability_store"):
        hits = service.hybrid_search("AAPL", collection="test", top_k=3)

    assert hits == [{"query": "AAPL", "collection": "test", "top_k": 3}]
    assert "private search run creation detail" not in caplog.text
    assert "[RAGObservability]" in caplog.text


def test_failed_search_recording_error_log_is_redacted(monkeypatch, caplog):
    class FailingStore:
        @staticmethod
        def begin_search_run(**_kwargs):
            return object()

        @staticmethod
        def complete_search_run(*_args, **_kwargs):
            raise RuntimeError("private failed-search recording detail")

    def ingest(_self, docs):
        return {"count": len(docs)}

    def search(_self, _query, *, collection, top_k=6):
        raise ValueError("private search execution detail")

    _install_test_hooks(
        monkeypatch,
        ingest=ingest,
        search=search,
        store=FailingStore(),
    )
    service = observability.HybridRAGService.__new__(observability.HybridRAGService)
    service.backend_name = "memory"

    with caplog.at_level(logging.ERROR, logger="backend.rag.observability_store"):
        with pytest.raises(ValueError, match="private search execution detail"):
            service.hybrid_search("AAPL", collection="test")

    assert "private failed-search recording detail" not in caplog.text
    assert "private search execution detail" not in caplog.text
    assert "[RAGObservability]" in caplog.text


def test_completed_search_recording_error_log_is_redacted(monkeypatch, caplog):
    class FailingStore:
        @staticmethod
        def begin_search_run(**_kwargs):
            return object()

        @staticmethod
        def complete_search_run(*_args, **_kwargs):
            raise RuntimeError("private completed-search recording detail")

    def ingest(_self, docs):
        return {"count": len(docs)}

    def search(_self, _query, *, collection, top_k=6):
        return [{"id": "hit-1"}]

    _install_test_hooks(
        monkeypatch,
        ingest=ingest,
        search=search,
        store=FailingStore(),
    )
    service = observability.HybridRAGService.__new__(observability.HybridRAGService)
    service.backend_name = "memory"

    with caplog.at_level(logging.ERROR, logger="backend.rag.observability_store"):
        hits = service.hybrid_search("AAPL", collection="test")

    assert hits == [{"id": "hit-1"}]
    assert "private completed-search recording detail" not in caplog.text
    assert "[RAGObservability]" in caplog.text
