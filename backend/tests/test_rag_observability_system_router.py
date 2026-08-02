# -*- coding: utf-8 -*-

from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.system_router import SystemRouterDeps, create_system_router


class _FakeRagStore:
    def __init__(self) -> None:
        self.last_runs_args: dict[str, object] | None = None
        self.last_db_browser_args: dict[str, object] | None = None

    def health_summary(self, recent_limit: int = 5, fallback_limit: int = 5) -> dict[str, object]:
        return {
            'enabled': True,
            'status': 'ok',
            'backend': 'postgres',
            'recent_run_count_24h': recent_limit,
            'recent_fallback_count_24h': fallback_limit,
            'recent_empty_hits_rate_24h': 0.0,
            'last_run_at': '2026-03-06T00:00:00Z',
            'last_fallback_at': None,
            'recent_runs': [],
            'fallback_summary': [],
        }

    def list_runs(self, *, limit: int = 20, cursor: str | None = None, q: str | None = None, fallback_only: bool = False) -> dict[str, object]:
        self.last_runs_args = {
            'limit': limit,
            'cursor': cursor,
            'q': q,
            'fallback_only': fallback_only,
        }
        return {
            'items': [
                {
                    'id': 'run-1',
                    'query_text': 'AAPL earnings outlook',
                    'fallback_reason': 'secret fallback reason',
                    'error_message': 'secret error message',
                    'status': 'success',
                    'backend_actual': 'postgres',
                    'retrieval_hit_count': 3,
                }
            ],
            'next_cursor': None,
        }

    def get_run_detail(self, run_id: str) -> dict[str, object] | None:
        if run_id != 'run-1':
            return None
        return {
            'id': 'run-1',
            'query_text': 'AAPL earnings outlook',
            'fallback_reason': 'secret fallback reason',
            'error_message': 'secret error message',
            'status': 'success',
            'backend_actual': 'postgres',
            'collection': 'finance-news',
        }

    def list_events(self, *, run_id: str, limit: int = 500) -> dict[str, object]:
        return {
            'items': [
                {
                    'id': 'evt-1',
                    'run_id': run_id,
                    'seq_no': 1,
                    'event_type': 'query_received',
                    'payload_json': {'query_preview': 'secret query', 'top_k': limit},
                }
            ],
            'next_cursor': None,
        }

    def list_documents(self, **_: object) -> dict[str, object]:
        return {'items': [{'id': 'doc-1', 'content_raw': 'secret raw document'}], 'next_cursor': None}

    def list_chunks(self, **_: object) -> dict[str, object]:
        return {'items': [{'id': 'chunk-1', 'chunk_text': 'secret chunk'}], 'next_cursor': None}

    def list_hits(self, **_: object) -> dict[str, object]:
        return {
            'items': [
                {
                    'id': 'hit-1',
                    'chunk_text': 'secret hit chunk',
                    'chunk_preview': 'secret hit preview',
                    'rrf_score': 0.75,
                }
            ],
            'next_cursor': None,
        }

    def list_collections(self, *, limit: int = 200) -> dict[str, object]:
        return {
            'items': [
                {
                    'collection': 'finance-news',
                    'run_count': 2,
                    'document_count': limit,
                    'chunk_count': 63,
                    'latest_run_at': '2026-03-07T00:00:00Z',
                    'latest_document_at': '2026-03-06T00:00:00Z',
                    'row_count': limit,
                    'last_run_at': '2026-03-07T00:00:00Z',
                    'last_created_at': '2026-03-06T00:00:00Z',
                    'synthetic_backfill_run_id': 'run-backfill-1',
                    'synthetic_backfill_started_at': '2026-03-07T01:45:32Z',
                }
            ]
        }

    def browse_db_table(self, *, table_name: str, limit: int = 50, offset: int = 0, q: str | None = None, collection: str | None = None, run_id: str | None = None, source_doc_id: str | None = None) -> dict[str, object]:
        self.last_db_browser_args = {
            'table_name': table_name,
            'limit': limit,
            'offset': offset,
            'q': q,
            'collection': collection,
            'run_id': run_id,
            'source_doc_id': source_doc_id,
        }
        return {
            'table': table_name,
            'columns': ['id', 'collection', 'chunk_text'],
            'items': [{'id': 'row-1', 'collection': collection or 'finance-news', 'chunk_text': 'secret chunk'}],
            'total': 1,
            'limit': limit,
            'offset': offset,
            'has_more': False,
        }

    def search_preview(self, *, query: str, collection: str, top_k: int = 10) -> list[dict[str, object]]:
        return [
            {
                'query': query,
                'collection': collection,
                'top_k': top_k,
                'content': 'secret search content',
                'rrf_score': 0.75,
            }
        ]

    def soft_delete_run(self, run_id: str, deleted_by: str = 'system', reason: str | None = None) -> dict[str, object] | None:
        return {'id': run_id, 'deleted_by': deleted_by, 'reason': reason}

    def soft_delete_source_doc(self, source_doc_id: str, deleted_by: str = 'system', reason: str | None = None) -> dict[str, object] | None:
        return {'id': source_doc_id, 'deleted_by': deleted_by, 'reason': reason}


def _build_client(
    store: _FakeRagStore,
    *,
    graph_runner_ready: bool = True,
    checkpointer_backend: str = 'memory',
) -> TestClient:
    app = FastAPI()
    app.include_router(
        create_system_router(
            SystemRouterDeps(
                metrics_enabled=False,
                metrics_payload=lambda: ('', 'text/plain'),
                graph_runner_ready=lambda: graph_runner_ready,
                get_graph_checkpointer_info=lambda: {'backend': checkpointer_backend},
                get_orchestrator_safe=lambda: SimpleNamespace(cache=object(), tools_module=object()),
                get_planner_ab_metrics=lambda: {'enabled': False, 'split_percent': 0, 'variants': {'A': 0, 'B': 0}},
                get_rag_observability_store=lambda: store,
                require_rag_read_access=lambda _request: {'user_id': 'user-test', 'auth_type': 'test', 'role': 'reader'},
                require_rag_mutation_access=lambda _request: {'user_id': 'internal', 'auth_type': 'test', 'role': 'internal'},
                memory_service=object(),
                logger=None,
            )
        )
    )
    return TestClient(app)


def test_internal_health_degrades_when_graph_runner_is_not_ready(monkeypatch):
    monkeypatch.setenv('RAG_V2_BACKEND', 'auto')
    client = _build_client(_FakeRagStore(), graph_runner_ready=False)

    response = client.get('/internal/health')

    assert response.status_code == 200
    payload = response.json()
    assert payload['status'] == 'degraded'
    assert payload['components']['langgraph_runner']['status'] == 'initializing'


def test_internal_health_degrades_when_checkpointer_is_not_ready(monkeypatch):
    monkeypatch.setenv('RAG_V2_BACKEND', 'auto')
    client = _build_client(_FakeRagStore(), checkpointer_backend='unknown')

    response = client.get('/internal/health')

    assert response.status_code == 200
    payload = response.json()
    assert payload['status'] == 'degraded'
    assert payload['components']['checkpointer']['status'] == 'initializing'


def test_rag_status_endpoint_returns_health_summary():
    client = _build_client(_FakeRagStore())

    response = client.get('/diagnostics/rag/status')

    assert response.status_code == 200
    payload = response.json()
    assert payload['status'] == 'ok'
    assert payload['data']['enabled'] is True
    assert payload['data']['backend'] == 'postgres'


def test_rag_status_projects_store_fields_for_reader():
    secret = 'private-store-field'

    class _ProjectionStore(_FakeRagStore):
        def health_summary(self, recent_limit: int = 5, fallback_limit: int = 5) -> dict[str, object]:
            payload = super().health_summary(recent_limit, fallback_limit)
            payload['future_store_field'] = secret
            payload['recent_runs'] = [{'id': 'run-1', 'query_text': secret, 'status': 'success'}]
            return payload

    client = _build_client(_ProjectionStore())
    response = client.get('/diagnostics/rag/status')

    assert response.status_code == 200
    observability = response.json()['data']['observability']
    assert set(observability) == {
        'status',
        'enabled',
        'backend',
        'recent_run_count_24h',
        'recent_fallback_count_24h',
        'recent_empty_hits_rate_24h',
        'last_run_at',
        'last_fallback_at',
        'recent_runs',
        'fallback_summary',
    }
    assert secret not in response.text


def test_rag_runs_endpoint_returns_items_and_passes_filters():
    store = _FakeRagStore()
    client = _build_client(store)

    response = client.get('/diagnostics/rag/runs', params={'limit': 15, 'q': 'AAPL', 'fallback_only': 'true'})

    assert response.status_code == 200
    payload = response.json()
    assert payload['status'] == 'ok'
    assert payload['data']['items'][0]['id'] == 'run-1'
    assert store.last_runs_args == {'limit': 15, 'cursor': None, 'q': 'AAPL', 'fallback_only': True}


def test_rag_run_detail_endpoint_returns_item_and_404_for_missing_run():
    client = _build_client(_FakeRagStore())

    ok_response = client.get('/diagnostics/rag/runs/run-1')
    missing_response = client.get('/diagnostics/rag/runs/run-missing')

    assert ok_response.status_code == 200
    assert ok_response.json()['data']['collection'] == 'finance-news'
    assert missing_response.status_code == 404
    assert missing_response.json()['detail'] == 'run not found'


def test_rag_collections_endpoint_returns_collection_summary():
    client = _build_client(_FakeRagStore())

    response = client.get('/diagnostics/rag/collections', params={'limit': 12})

    assert response.status_code == 200
    payload = response.json()
    assert payload['status'] == 'ok'
    assert payload['data']['items'][0]['collection'] == 'finance-news'
    assert payload['data']['items'][0]['run_count'] == 2
    assert payload['data']['items'][0]['document_count'] == 12
    assert payload['data']['items'][0]['chunk_count'] == 63
    assert payload['data']['items'][0]['row_count'] == 12
    assert payload['data']['items'][0]['synthetic_backfill_run_id'] == 'run-backfill-1'
    assert payload['data']['items'][0]['synthetic_backfill_started_at'] == '2026-03-07T01:45:32Z'


def test_rag_db_browser_endpoint_returns_rows_and_passes_filters():
    store = _FakeRagStore()
    client = _build_client(store)

    response = client.get(
        '/diagnostics/rag/db-browser/rag_chunks',
        params={
            'limit': 25,
            'offset': 50,
            'q': 'apple',
            'collection': 'local-test',
            'run_id': 'run-1',
            'source_doc_id': 'doc-1',
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload['status'] == 'ok'
    assert payload['data']['table'] == 'rag_chunks'
    assert payload['data']['columns'] == ['id', 'collection']
    assert payload['data']['items'][0]['id'] == 'row-1'
    assert 'chunk_text' not in payload['data']['items'][0]
    assert store.last_db_browser_args == {
        'table_name': 'rag_chunks',
        'limit': 25,
        'offset': 50,
        'q': 'apple',
        'collection': 'local-test',
        'run_id': 'run-1',
        'source_doc_id': 'doc-1',
    }


def test_rag_raw_fields_require_admin_include():
    reader = _build_client(_FakeRagStore())
    reader_response = reader.get('/diagnostics/rag/chunks', params={'include': 'raw'})
    assert reader_response.status_code == 200
    assert 'chunk_text' not in str(reader_response.json())
    reader_events = reader.get('/diagnostics/rag/runs/run-1/events', params={'include': 'raw'})
    assert reader_events.status_code == 200
    assert 'query_preview' not in str(reader_events.json())
    assert reader_events.json()['data']['items'][0]['payload_json']['top_k'] == 500
    reader_hits = reader.get('/diagnostics/rag/hits', params={'include': 'raw'})
    assert reader_hits.status_code == 200
    assert 'secret hit' not in reader_hits.text
    assert reader_hits.json()['data']['items'][0]['rrf_score'] == 0.75
    reader_preview = reader.post(
        '/diagnostics/rag/search-preview',
        params={'include': 'raw'},
        json={'query': 'secret search query', 'collection': 'finance-news', 'top_k': 3},
    )
    assert reader_preview.status_code == 200
    assert 'secret search' not in reader_preview.text
    assert reader_preview.json()['data'][0]['rrf_score'] == 0.75
    reader_runs = reader.get('/diagnostics/rag/runs', params={'include': 'raw'})
    assert reader_runs.status_code == 200
    assert 'secret fallback reason' not in reader_runs.text
    assert 'secret error message' not in reader_runs.text
    reader_run = reader.get('/diagnostics/rag/runs/run-1', params={'include': 'raw'})
    assert reader_run.status_code == 200
    assert 'secret fallback reason' not in reader_run.text
    assert 'secret error message' not in reader_run.text

    app = FastAPI()
    app.include_router(
        create_system_router(
            SystemRouterDeps(
                metrics_enabled=False,
                metrics_payload=lambda: ('', 'text/plain'),
                graph_runner_ready=lambda: True,
                get_graph_checkpointer_info=lambda: {'backend': 'memory'},
                get_orchestrator_safe=lambda: None,
                get_planner_ab_metrics=lambda: {},
                get_rag_observability_store=lambda: _FakeRagStore(),
                require_rag_read_access=lambda _request: {'user_id': 'admin', 'auth_type': 'test', 'role': 'admin'},
                require_rag_mutation_access=lambda _request: {'user_id': 'admin', 'auth_type': 'test', 'role': 'admin'},
                memory_service=object(),
                logger=None,
            )
        )
    )
    admin = TestClient(app)
    admin_response = admin.get('/diagnostics/rag/chunks', params={'include': 'raw'})
    assert admin_response.status_code == 200
    assert 'chunk_text' in str(admin_response.json())
    admin_events = admin.get('/diagnostics/rag/runs/run-1/events', params={'include': 'raw'})
    assert admin_events.status_code == 200
    assert admin_events.json()['data']['items'][0]['payload_json']['query_preview'] == 'secret query'
    admin_hits = admin.get('/diagnostics/rag/hits', params={'include': 'raw'})
    assert admin_hits.status_code == 200
    assert admin_hits.json()['data']['items'][0]['chunk_text'] == 'secret hit chunk'
    admin_preview = admin.post(
        '/diagnostics/rag/search-preview',
        params={'include': 'raw'},
        json={'query': 'secret search query', 'collection': 'finance-news', 'top_k': 3},
    )
    assert admin_preview.status_code == 200
    assert admin_preview.json()['data'][0]['content'] == 'secret search content'
    admin_runs = admin.get('/diagnostics/rag/runs', params={'include': 'raw'})
    assert admin_runs.status_code == 200
    assert admin_runs.json()['data']['items'][0]['fallback_reason'] == 'secret fallback reason'
    assert admin_runs.json()['data']['items'][0]['error_message'] == 'secret error message'


def test_internal_health_projects_stable_redacted_rag_observability(monkeypatch):
    secret = 'private-rag-observability-secret'

    class _ProjectionStore(_FakeRagStore):
        def health_summary(self, recent_limit: int = 5, fallback_limit: int = 5) -> dict[str, object]:
            return {
                'enabled': True,
                'status': 'ok',
                'backend': 'postgres',
                'recent_run_count_24h': recent_limit,
                'recent_fallback_count_24h': fallback_limit,
                'recent_empty_hits_rate_24h': 0.25,
                'last_run_at': '2026-03-06T00:00:00Z',
                'last_fallback_at': '2026-03-05T00:00:00Z',
                'future_store_field': secret,
                'recent_runs': [
                    {
                        'id': 'run-1',
                        'collection': 'finance-news',
                        'backend_requested': 'postgres',
                        'backend_actual': 'postgres',
                        'status': 'fallback',
                        'retrieval_hit_count': 3,
                        'source_doc_count': 2,
                        'chunk_count': 5,
                        'started_at': '2026-03-06T00:00:00Z',
                        'finished_at': '2026-03-06T00:00:01Z',
                        'latency_ms': 1000,
                        'query_text': secret,
                        'fallback_reason': secret,
                        'error_message': secret,
                        'metadata_json': secret,
                    }
                ],
                'fallback_summary': [
                    {
                        'reason_code': 'backend_timeout',
                        'backend_before': 'postgres',
                        'backend_after': 'memory',
                        'count': 1,
                        'latest_at': '2026-03-06T00:00:01Z',
                        'reason_text': secret,
                        'payload_json': secret,
                    }
                ],
            }

    from backend.rag import hybrid_service

    monkeypatch.setenv('RAG_V2_BACKEND', 'auto')
    monkeypatch.setattr(
        hybrid_service,
        'get_rag_service',
        lambda: SimpleNamespace(
            backend_name='memory',
            embedding_model='hash',
            vector_dim=96,
            count_documents=lambda: 0,
            fallback_reason=None,
        ),
    )

    with _build_client(_ProjectionStore()) as client:
        response = client.get('/internal/health')

    assert response.status_code == 200
    payload = response.json()
    observability = payload['components']['rag_observability']
    assert set(observability) == {
        'status',
        'enabled',
        'backend',
        'recent_run_count_24h',
        'recent_fallback_count_24h',
        'recent_empty_hits_rate_24h',
        'last_run_at',
        'last_fallback_at',
        'recent_runs',
        'fallback_summary',
    }
    assert set(observability['recent_runs'][0]) == {
        'id',
        'collection',
        'backend_requested',
        'backend_actual',
        'status',
        'retrieval_hit_count',
        'source_doc_count',
        'chunk_count',
        'started_at',
        'finished_at',
        'latency_ms',
    }
    assert set(observability['fallback_summary'][0]) == {
        'reason_code',
        'backend_before',
        'backend_after',
        'count',
        'latest_at',
    }
    assert payload['components']['rag']['recent_runs'] == observability['recent_runs']
    assert payload['components']['rag']['fallback_summary'] == observability['fallback_summary']
    assert secret not in response.text


def test_rag_diagnostics_reject_oversized_search_filters():
    client = _build_client(_FakeRagStore())

    runs_response = client.get('/diagnostics/rag/runs', params={'q': 'x' * 2049})
    browser_response = client.get(
        '/diagnostics/rag/db-browser/rag_documents_v2',
        params={'collection': 'x' * 257},
    )
    preview_response = client.post(
        '/diagnostics/rag/search-preview',
        json={'query': 'x' * 2049, 'collection': 'finance-news', 'top_k': 10},
    )
    top_k_response = client.post(
        '/diagnostics/rag/search-preview',
        json={'query': 'AAPL', 'collection': 'finance-news', 'top_k': 101},
    )

    assert runs_response.status_code == 422
    assert browser_response.status_code == 422
    assert preview_response.status_code == 400
    assert top_k_response.status_code == 400


def test_rag_diagnostics_reject_oversized_soft_delete_metadata():
    client = _build_client(_FakeRagStore())

    run_id_response = client.post(
        f"/diagnostics/rag/runs/{'x' * 257}/soft-delete",
        json={"reason": "cleanup"},
    )
    reason_response = client.post(
        "/diagnostics/rag/runs/run-1/soft-delete",
        json={"reason": "x" * 1001},
    )
    actor_response = client.post(
        "/diagnostics/rag/documents/doc-1/soft-delete",
        json={"deleted_by": "x" * 129},
    )

    assert run_id_response.status_code == 422
    assert reason_response.status_code == 422
    assert actor_response.status_code == 422
