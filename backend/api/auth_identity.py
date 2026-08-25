"""RAG observability identity/auth helpers (extracted from api/main.py)."""

from __future__ import annotations

import hashlib
import os
import time
from threading import Lock
from typing import Any, Dict, Optional
from urllib import error as urllib_error
from urllib import request as urllib_request

from fastapi import HTTPException, Request

from backend.api.security_config import (
    extract_api_key as _extract_api_key,
    extract_bearer_token as _extract_bearer_token,
    parse_api_keys as _parse_api_keys,
)
from backend.security.auth import (
    env_bool as _auth_env_bool,
    secure_secret_in,
    secure_secret_matches,
)
from backend.utils.strict_json import json_loads_strict


_AUTH_IDENTITY_CACHE_SENTINEL = object()
_auth_identity_cache: Dict[str, tuple[float, Optional[Dict[str, Any]]]] = {}
_auth_identity_lock = Lock()


def _env_bool(key: str, default: str = "false") -> bool:
    return _auth_env_bool(key, default)


def _resolve_supabase_auth_config() -> tuple[str, str]:
    supabase_url = str(os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL") or "").strip().rstrip("/")
    publishable_key = str(os.getenv("SUPABASE_PUBLISHABLE_KEY") or os.getenv("VITE_SUPABASE_PUBLISHABLE_KEY") or "").strip()
    return supabase_url, publishable_key


def _is_supabase_auth_configured() -> bool:
    supabase_url, publishable_key = _resolve_supabase_auth_config()
    return bool(supabase_url and publishable_key)


def _resolve_rag_observability_dev_auth_config() -> tuple[str, str, Optional[str]]:
    token = str(os.getenv("RAG_OBSERVABILITY_DEV_ACCESS_TOKEN") or "").strip()
    user_id = str(os.getenv("RAG_OBSERVABILITY_DEV_USER_ID") or "local-rag-inspector").strip() or "local-rag-inspector"
    email_raw = str(os.getenv("RAG_OBSERVABILITY_DEV_EMAIL") or "local-rag@example.com").strip()
    return token, user_id, email_raw or None


def _is_rag_observability_dev_auth_enabled() -> bool:
    token, _, _ = _resolve_rag_observability_dev_auth_config()
    return _env_bool("RAG_OBSERVABILITY_DEV_AUTH_ENABLED", "false") and bool(token)


def _resolve_rag_observability_dev_user_identity(token: str) -> Optional[Dict[str, Any]]:
    normalized = str(token or "").strip()
    if not normalized or not _is_rag_observability_dev_auth_enabled():
        return None

    dev_token, user_id, email = _resolve_rag_observability_dev_auth_config()
    if not secure_secret_matches(normalized, dev_token):
        return None

    return {
        "user_id": user_id,
        "email": email,
        "auth_type": "dev_bearer",
        "role": "reader",
    }


def _is_internal_api_key_authorized(request: Request) -> bool:
    api_key = _extract_api_key(request)
    return bool(api_key and secure_secret_in(api_key, _parse_api_keys()))


def _auth_identity_cache_ttl_seconds() -> int:
    raw = str(os.getenv("RAG_OBSERVABILITY_AUTH_CACHE_SECONDS", "60") or "60").strip()
    try:
        value = int(raw)
    except Exception:
        value = 60
    return max(5, min(600, value))


def _auth_identity_cache_max_entries() -> int:
    raw = str(os.getenv("RAG_OBSERVABILITY_AUTH_CACHE_MAX_ENTRIES", "1000") or "1000").strip()
    try:
        value = int(raw)
    except Exception:
        value = 1000
    return max(1, min(10000, value))


def _auth_token_cache_key(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _prune_auth_identity_cache(now: float, *, incoming_key: str | None = None) -> None:
    expired = [key for key, (expires_at, _) in _auth_identity_cache.items() if expires_at <= now]
    for key in expired:
        _auth_identity_cache.pop(key, None)

    max_entries = _auth_identity_cache_max_entries()
    if incoming_key in _auth_identity_cache or len(_auth_identity_cache) < max_entries:
        return
    oldest_key = min(_auth_identity_cache, key=lambda key: _auth_identity_cache[key][0])
    _auth_identity_cache.pop(oldest_key, None)


def _fetch_supabase_user_identity(token: str) -> Optional[Dict[str, Any]]:
    normalized = str(token or "").strip()
    if not normalized:
        return None

    now = time.time()
    cache_key = _auth_token_cache_key(normalized)
    with _auth_identity_lock:
        _prune_auth_identity_cache(now, incoming_key=cache_key)
        cached = _auth_identity_cache.get(cache_key)
        if cached:
            return cached[1]

    supabase_url, publishable_key = _resolve_supabase_auth_config()
    if not supabase_url or not publishable_key:
        raise RuntimeError("RAG diagnostics auth not configured")

    request_obj = urllib_request.Request(
        f"{supabase_url}/auth/v1/user",
        headers={
            "Authorization": f"Bearer {normalized}",
            "apikey": publishable_key,
            "Accept": "application/json",
        },
        method="GET",
    )

    user_identity: Optional[Dict[str, Any]] = None
    try:
        with urllib_request.urlopen(request_obj, timeout=5) as response:
            payload = json_loads_strict(response.read().decode("utf-8") or "{}")
        user_id = str(payload.get("id") or "").strip() if isinstance(payload, dict) else ""
        if user_id:
            email = payload.get("email") if isinstance(payload, dict) else None
            user_identity = {
                "user_id": user_id,
                "email": str(email).strip() if email else None,
                "auth_type": "supabase",
                "role": "reader",
            }
    except urllib_error.HTTPError as exc:
        if exc.code not in (401, 403):
            raise RuntimeError(f"Supabase auth lookup failed with HTTP {exc.code}") from exc
    except urllib_error.URLError as exc:
        raise RuntimeError(f"Supabase auth lookup failed: {exc.reason}") from exc

    with _auth_identity_lock:
        _prune_auth_identity_cache(now, incoming_key=cache_key)
        _auth_identity_cache[cache_key] = (now + _auth_identity_cache_ttl_seconds(), user_identity)
    return user_identity


def _resolve_request_user_identity(request: Request) -> Optional[Dict[str, Any]]:
    cached = getattr(request.state, "rag_authenticated_user", _AUTH_IDENTITY_CACHE_SENTINEL)
    if cached is not _AUTH_IDENTITY_CACHE_SENTINEL:
        return cached

    token = _extract_bearer_token(request)
    if not token:
        request.state.rag_authenticated_user = None
        return None

    dev_identity = _resolve_rag_observability_dev_user_identity(token)
    if dev_identity:
        request.state.rag_authenticated_user = dev_identity
        return dev_identity

    if not _is_supabase_auth_configured():
        request.state.rag_authenticated_user = None
        return None

    user_identity = _fetch_supabase_user_identity(token)
    request.state.rag_authenticated_user = user_identity
    return user_identity


def _require_rag_read_access(request: Request) -> Dict[str, Any]:
    if _is_internal_api_key_authorized(request):
        principal = {"user_id": "internal", "email": None, "auth_type": "api_key", "role": "internal"}
        request.state.rag_authenticated_user = principal
        return principal

    if not (_is_supabase_auth_configured() or _is_rag_observability_dev_auth_enabled()):
        raise HTTPException(status_code=503, detail="RAG diagnostics auth not configured")

    user_identity = _resolve_request_user_identity(request)
    if user_identity:
        return user_identity
    raise HTTPException(status_code=401, detail="Authentication required")
