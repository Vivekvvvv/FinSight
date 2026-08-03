# -*- coding: utf-8 -*-

from __future__ import annotations

import logging

from fastapi.testclient import TestClient


class _FakeRagStore:
    def health_summary(self, recent_limit: int = 5, fallback_limit: int = 5) -> dict[str, object]:
        return {
            'enabled': True,
            'status': 'ok',
            'backend': 'postgres',
            'recent_run_count_24h': recent_limit,
            'recent_fallback_count_24h': fallback_limit,
            'recent_runs': [],
            'fallback_summary': [],
        }

    def soft_delete_run(self, run_id: str, deleted_by: str = 'system', reason: str | None = None) -> dict[str, object] | None:
        return {'id': run_id, 'deleted_by': deleted_by, 'reason': reason}

    def soft_delete_source_doc(self, source_doc_id: str, deleted_by: str = 'system', reason: str | None = None) -> dict[str, object] | None:
        return {'id': source_doc_id, 'deleted_by': deleted_by, 'reason': reason}


def _configure_auth(monkeypatch):
    from backend.api import main

    monkeypatch.setenv('VITE_SUPABASE_URL', 'https://supabase.test')
    monkeypatch.setenv('VITE_SUPABASE_PUBLISHABLE_KEY', 'sb_publishable_test')
    monkeypatch.setattr(main, '_rate_limiter', main.SimpleRateLimiter(limit_per_window=100, window_seconds=60, enabled=False))
    monkeypatch.setattr(main, '_rag_auth_rate_limiter', main.SimpleRateLimiter(limit_per_window=100, window_seconds=60, enabled=False))
    monkeypatch.setattr(main, 'get_rag_observability_store', lambda: _FakeRagStore())
    main._auth_identity_cache.clear()
    return main


def test_rag_diagnostics_read_requires_logged_in_user(monkeypatch):
    main = _configure_auth(monkeypatch)
    monkeypatch.setenv('API_AUTH_ENABLED', 'false')

    with TestClient(main.app) as client:
        response = client.get('/diagnostics/rag/status')

    assert response.status_code == 401
    assert response.json().get('detail') == 'Authentication required'


def test_orchestrator_and_planner_diagnostics_require_logged_in_user(monkeypatch):
    main = _configure_auth(monkeypatch)
    monkeypatch.setenv('API_AUTH_ENABLED', 'false')

    with TestClient(main.app) as client:
        for path in ('/diagnostics/orchestrator', '/diagnostics/planner-ab', '/diagnostics/planner_ab'):
            response = client.get(path)
            assert response.status_code == 401
            assert response.json().get('detail') == 'Authentication required'


def test_planner_diagnostics_allows_bearer_user_even_when_api_auth_enabled(monkeypatch):
    main = _configure_auth(monkeypatch)
    monkeypatch.setenv('API_AUTH_ENABLED', 'true')
    monkeypatch.setenv('API_AUTH_KEYS', 'release-key-1')
    monkeypatch.setattr(
        main,
        '_fetch_supabase_user_identity',
        lambda token: {'user_id': f'user:{token}', 'email': 'reader@example.com', 'auth_type': 'supabase', 'role': 'reader'},
    )

    with TestClient(main.app) as client:
        for path in ('/diagnostics/planner-ab', '/diagnostics/planner_ab'):
            response = client.get(path, headers={'Authorization': 'Bearer access-token-reader'})
            assert response.status_code == 200
            assert response.json()['status'] == 'ok'


def test_internal_health_requires_internal_api_key(monkeypatch):
    main = _configure_auth(monkeypatch)
    monkeypatch.setenv('DEV_MODE', 'true')
    monkeypatch.setenv('API_AUTH_KEYS', 'internal-health-key')
    monkeypatch.setattr(
        main,
        '_fetch_supabase_user_identity',
        lambda token: {'user_id': f'user:{token}', 'email': 'reader@example.com', 'auth_type': 'supabase', 'role': 'reader'},
    )

    with TestClient(main.app) as client:
        for path in ('/internal/health', '/admin/health'):
            missing = client.get(path)
            invalid = client.get(path, headers={'x-api-key': 'wrong-key'})
            reader = client.get(path, headers={'Authorization': 'Bearer access-token-reader'})
            internal = client.get(path, headers={'x-api-key': 'internal-health-key'})

            assert missing.status_code == 403
            assert invalid.status_code == 403
            assert reader.status_code == 403
            assert internal.status_code == 200
            assert internal.json()['status'] in {'healthy', 'degraded'}


def test_rag_diagnostics_read_allows_bearer_user_even_when_api_auth_enabled(monkeypatch):
    main = _configure_auth(monkeypatch)
    monkeypatch.setenv('API_AUTH_ENABLED', 'true')
    monkeypatch.setenv('API_AUTH_KEYS', 'release-key-1')
    monkeypatch.setattr(
        main,
        '_fetch_supabase_user_identity',
        lambda token: {'user_id': f'user:{token}', 'email': 'reader@example.com', 'auth_type': 'supabase', 'role': 'reader'},
    )

    with TestClient(main.app) as client:
        response = client.get('/diagnostics/rag/status', headers={'Authorization': 'Bearer access-token-reader'})

    assert response.status_code == 200
    payload = response.json()
    assert payload['status'] == 'ok'
    assert payload['data']['enabled'] is True


def test_rag_diagnostics_soft_delete_is_read_only_for_logged_in_user(monkeypatch):
    main = _configure_auth(monkeypatch)
    monkeypatch.setenv('API_AUTH_ENABLED', 'false')
    monkeypatch.setattr(
        main,
        '_fetch_supabase_user_identity',
        lambda token: {'user_id': f'user:{token}', 'email': 'reader@example.com', 'auth_type': 'supabase', 'role': 'reader'},
    )

    with TestClient(main.app) as client:
        response = client.post(
            '/diagnostics/rag/runs/run-1/soft-delete',
            headers={'Authorization': 'Bearer access-token-readonly'},
            json={'deleted_by': 'reader'},
        )

    assert response.status_code == 403
    assert 'read-only' in str(response.json().get('detail', '')).lower()


def test_rag_diagnostics_soft_delete_allows_internal_api_key(monkeypatch):
    main = _configure_auth(monkeypatch)
    monkeypatch.setenv('API_AUTH_ENABLED', 'false')
    monkeypatch.setenv('API_AUTH_KEYS', 'release-key-1')

    with TestClient(main.app) as client:
        response = client.post(
            '/diagnostics/rag/runs/run-1/soft-delete',
            headers={'x-api-key': 'release-key-1'},
            json={'deleted_by': 'ops-user', 'reason': 'retention drill'},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload['status'] == 'ok'
    assert payload['data']['id'] == 'run-1'
    assert payload['data']['deleted_by'] == 'ops-user'

def test_rag_diagnostics_read_allows_local_dev_bearer_without_supabase(monkeypatch):
    from backend.api import main

    monkeypatch.delenv('VITE_SUPABASE_URL', raising=False)
    monkeypatch.delenv('VITE_SUPABASE_PUBLISHABLE_KEY', raising=False)
    monkeypatch.delenv('SUPABASE_URL', raising=False)
    monkeypatch.delenv('SUPABASE_PUBLISHABLE_KEY', raising=False)
    monkeypatch.setenv('API_AUTH_ENABLED', 'false')
    monkeypatch.setenv('RAG_OBSERVABILITY_DEV_AUTH_ENABLED', 'true')
    monkeypatch.setenv('RAG_OBSERVABILITY_DEV_ACCESS_TOKEN', 'local-rag-dev-token')
    monkeypatch.setenv('RAG_OBSERVABILITY_DEV_USER_ID', 'dev-rag-user')
    monkeypatch.setenv('RAG_OBSERVABILITY_DEV_EMAIL', 'dev-rag@example.com')
    monkeypatch.setattr(main, '_rate_limiter', main.SimpleRateLimiter(limit_per_window=100, window_seconds=60, enabled=False))
    monkeypatch.setattr(main, '_rag_auth_rate_limiter', main.SimpleRateLimiter(limit_per_window=100, window_seconds=60, enabled=False))
    monkeypatch.setattr(main, 'get_rag_observability_store', lambda: _FakeRagStore())
    main._auth_identity_cache.clear()

    with TestClient(main.app) as client:
        response = client.get('/diagnostics/rag/status', headers={'Authorization': 'Bearer local-rag-dev-token'})

    assert response.status_code == 200
    payload = response.json()
    assert payload['status'] == 'ok'
    assert payload['data']['enabled'] is True
    assert payload['data']['backend'] == 'postgres'


def test_rag_auth_upstream_error_log_is_redacted(monkeypatch, caplog):
    main = _configure_auth(monkeypatch)

    def fail_access(_request):
        raise RuntimeError("private auth upstream detail")

    monkeypatch.setattr(main, '_require_rag_read_access', fail_access)
    with caplog.at_level(logging.ERROR, logger='backend.api.main'):
        with TestClient(main.app) as client:
            response = client.get('/diagnostics/rag/status')

    assert response.status_code == 503
    assert response.json()['detail'] == 'Auth upstream unavailable'
    assert 'private auth upstream detail' not in caplog.text
    assert 'rag access check failed due to upstream auth error' in caplog.text


def test_rag_auth_preflight_rate_limit_runs_before_upstream_auth(monkeypatch):
    from fastapi import HTTPException

    main = _configure_auth(monkeypatch)
    monkeypatch.setattr(
        main,
        '_rag_auth_rate_limiter',
        main.SimpleRateLimiter(limit_per_window=1, window_seconds=60, enabled=True),
    )
    calls = []

    def deny(_request):
        calls.append(True)
        raise HTTPException(status_code=401, detail='Authentication required')

    monkeypatch.setattr(main, '_require_rag_read_access', deny)
    with TestClient(main.app) as client:
        first = client.get('/diagnostics/rag/status')
        second = client.get('/diagnostics/rag/status')

    assert first.status_code == 401
    assert second.status_code == 429
    assert second.headers['Retry-After']
    assert len(calls) == 1


def test_rag_auth_cache_hashes_tokens_and_enforces_capacity(monkeypatch):
    main = _configure_auth(monkeypatch)
    monkeypatch.setenv('RAG_OBSERVABILITY_AUTH_CACHE_MAX_ENTRIES', '2')

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"id":"user-1","email":"reader@example.com"}'

    monkeypatch.setattr(main.urllib_request, 'urlopen', lambda *_args, **_kwargs: _Response())
    raw_tokens = ['private-token-a', 'private-token-b', 'private-token-c']
    for token in raw_tokens:
        assert main._fetch_supabase_user_identity(token)['user_id'] == 'user-1'

    assert len(main._auth_identity_cache) == 2
    assert all(token not in main._auth_identity_cache for token in raw_tokens)
    assert all(len(key) == 64 for key in main._auth_identity_cache)
