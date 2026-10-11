# -*- coding: utf-8 -*-
from __future__ import annotations

import functools
import logging
import os
import threading
import time
from collections.abc import Iterable
from typing import Any

from backend.rag.hybrid_service import HybridRAGService, RAGDocument, get_rag_service
from backend.rag.observability_models import (
    ChunkRecord,
    FallbackEventRecord,
    PendingIngestBatch,
    PendingIngestDocRecord,
    QueryEventRecord,
    QueryRunRecord,
    RetrievalHitRecord,
    SearchRunContext,
    SourceDocRecord,
)
from backend.rag.observability_runtime import (
    _resolve_dsn,
    _store_lock,
)
from backend.utils.quote import safe_int

from backend.rag.observability_sql_store import (
    NoOpRAGObservabilityStore,
    SQLRAGObservabilityStore,
    _DB_BROWSER_TABLES,
    _RAG_RAW_COLUMNS,
    _chunk_params,
    _db_browser_available_columns,
    _db_browser_filter_sql,
    _db_browser_order_by_sql,
    _db_browser_search_sql,
    _decode_cursor,
    _doc_type_from_source,
    _encode_cursor,
    _finite_optional_float,
    _json_loads,
    _mapping_to_dict,
    _new_id,
    _project_db_browser_columns,
    _quote_identifier,
    _reject_json_constant,
    _sha256_text,
    _truncate,
)

logger = logging.getLogger(__name__)


RAGObservabilityStore = SQLRAGObservabilityStore
_store_singleton: SQLRAGObservabilityStore | NoOpRAGObservabilityStore | None = None
_hooks_lock = threading.Lock()
_hooks_installed = False


def get_rag_observability_store() -> SQLRAGObservabilityStore | NoOpRAGObservabilityStore:
    global _store_singleton
    if _store_singleton is not None:
        return _store_singleton
    with _store_lock:
        if _store_singleton is None:
            dsn = _resolve_dsn()
            _store_singleton = SQLRAGObservabilityStore(dsn=dsn) if dsn else NoOpRAGObservabilityStore()
    return _store_singleton


def reset_rag_observability_store_cache() -> None:
    global _store_singleton
    with _store_lock:
        _store_singleton = None


def install_rag_observability_hooks() -> bool:
    global _hooks_installed
    if _hooks_installed:
        return True
    with _hooks_lock:
        if _hooks_installed or getattr(HybridRAGService, "_rag_observability_hooks_installed", False):
            _hooks_installed = True
            return True
        original_ingest = HybridRAGService.ingest_documents
        original_search = HybridRAGService.hybrid_search

        @functools.wraps(original_ingest)
        def observed_ingest(self: HybridRAGService, docs: Iterable[RAGDocument]) -> dict[str, Any]:
            doc_list = list(docs or [])
            result = original_ingest(self, doc_list)
            if doc_list:
                try:
                    get_rag_observability_store().cache_ingest_batch(docs=doc_list, ingest_stats=result if isinstance(result, dict) else {"result": result}, backend_requested=str(os.getenv("RAG_V2_BACKEND", "auto")).strip().lower() or "auto", backend_actual=str(getattr(self, "backend_name", "unknown") or "unknown"))
                except Exception as exc:
                    logger.error('[RAGObservability] 缓存 ingest 批次失败')
            return result

        @functools.wraps(original_search)
        def observed_search(self: HybridRAGService, query: str, *, collection: str, top_k: int = 6) -> list[dict[str, Any]]:
            store = get_rag_observability_store()
            context: SearchRunContext | None = None
            try:
                context = store.begin_search_run(query=query, collection=collection, top_k=max(1, safe_int(top_k, 6)), backend_requested=str(os.getenv("RAG_V2_BACKEND", "auto")).strip().lower() or "auto", backend_actual=str(getattr(self, "backend_name", "unknown") or "unknown"), route_name="hybrid_search", router_decision="hybrid_search", fallback_reason=str(getattr(self, "fallback_reason", "") or "") or None, metadata_json={"embedding_model": getattr(self, "embedding_model", None), "vector_dim": getattr(self, "vector_dim", None)})
            except Exception as exc:
                logger.error('[RAGObservability] 创建查询运行失败')
            try:
                hits = original_search(self, query, collection=collection, top_k=top_k)
            except Exception as exc:
                if context is not None:
                    try:
                        store.complete_search_run(context, hits=None, error=exc)
                    except Exception as inner_exc:
                        logger.error('[RAGObservability] 记录失败查询时出错')
                raise
            if context is not None:
                try:
                    store.complete_search_run(context, hits=hits, error=None)
                except Exception as exc:
                    logger.error('[RAGObservability] 记录查询完成失败')
            return hits

        HybridRAGService.ingest_documents = observed_ingest
        HybridRAGService.hybrid_search = observed_search
        setattr(HybridRAGService, "_rag_observability_hooks_installed", True)
        _hooks_installed = True
        return True


__all__ = [
    "NoOpRAGObservabilityStore",
    "SQLRAGObservabilityStore",
    "RAGObservabilityStore",
    "get_rag_observability_store",
    "reset_rag_observability_store_cache",
    "install_rag_observability_hooks",
]
