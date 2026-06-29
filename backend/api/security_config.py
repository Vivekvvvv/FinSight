from __future__ import annotations

import logging
import os
import time
from collections import deque
from typing import Optional

from fastapi import Request

from backend.security.auth import env_bool, is_dev_mode

logger = logging.getLogger(__name__)

PRODUCTION_REQUIRED_ENV = (
    "OPENAI_COMPATIBLE_API_KEY",
    "OPENAI_COMPATIBLE_API_BASE",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "JWT_SECRET",
    "API_AUTH_KEYS",
)


def env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, default))
    except Exception:
        return default


def parse_csv_env(key: str, default: str) -> list[str]:
    raw = os.getenv(key, default)
    return [item.strip() for item in str(raw or "").split(",") if item.strip()]


def cors_allow_origins() -> list[str]:
    origins = parse_csv_env(
        "CORS_ALLOW_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174",
    )
    return origins or [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ]


def cors_allow_origin_regex() -> str | None:
    configured = str(os.getenv("CORS_ALLOW_ORIGIN_REGEX") or "").strip()
    if configured:
        return configured
    return r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"


def cors_allow_credentials() -> bool:
    allow_credentials = env_bool("CORS_ALLOW_CREDENTIALS", "false")
    origins = cors_allow_origins()
    if allow_credentials and "*" in origins:
        logger.warning("CORS_ALLOW_CREDENTIALS=true with wildcard origin is invalid. Force disabling credentials.")
        return False
    return allow_credentials


def parse_api_keys() -> set[str]:
    raw = os.getenv("API_AUTH_KEYS") or os.getenv("API_AUTH_KEY") or ""
    return {item.strip() for item in raw.split(",") if item.strip()}


def extract_api_key(request: Request) -> Optional[str]:
    header_key = request.headers.get("x-api-key") or request.headers.get("X-API-Key")
    if header_key:
        return header_key.strip()
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return None


def extract_bearer_token(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip() or None
    return None


def is_allowlisted_path(path: str) -> bool:
    defaults = "/health,/docs,/openapi.json,/redoc"
    configured = parse_csv_env("API_PUBLIC_PATHS", defaults)
    exact_paths: set[str] = set()
    prefix_paths: list[str] = []

    for entry in configured:
        normalized = entry if entry.startswith("/") else f"/{entry}"
        if normalized.endswith("/*"):
            base = normalized[:-2]
            if base:
                prefix_paths.append(base)
        elif normalized in ("/docs", "/redoc"):
            exact_paths.add(normalized)
            prefix_paths.append(normalized)
        else:
            exact_paths.add(normalized)

    if path in exact_paths:
        return True
    return any(path.startswith(prefix + "/") or path == prefix for prefix in prefix_paths)


def missing_production_env() -> list[str]:
    if is_dev_mode():
        return []
    return [key for key in PRODUCTION_REQUIRED_ENV if not str(os.getenv(key) or "").strip()]


def validate_production_runtime_config() -> None:
    if is_dev_mode():
        logger.warning("DEV_MODE ON ?? auth bypassed and rate limits disabled. Do not use in production.")
        return
    missing = missing_production_env()
    if missing:
        raise SystemExit("Missing required production environment variables: " + ", ".join(missing))


class SimpleRateLimiter:
    def __init__(self, limit_per_window: int, window_seconds: int, enabled: bool = True):
        self.enabled = enabled
        self.limit = max(1, int(limit_per_window))
        self.window_seconds = max(1, int(window_seconds))
        self._buckets: dict[str, deque[float]] = {}
        self._last_cleanup = time.time()

    def _cleanup(self, now: float) -> None:
        if now - self._last_cleanup < self.window_seconds:
            return
        self._last_cleanup = now
        stale_keys = [
            key for key, bucket in self._buckets.items()
            if not bucket or (now - bucket[-1] >= self.window_seconds)
        ]
        for key in stale_keys:
            self._buckets.pop(key, None)

    @classmethod
    def from_env(cls) -> "SimpleRateLimiter":
        enabled = (not is_dev_mode()) and env_bool("RATE_LIMIT_ENABLED", "true")
        limit = int(os.getenv("RATE_LIMIT_PER_MINUTE", "120"))
        window_seconds = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
        return cls(limit_per_window=limit, window_seconds=window_seconds, enabled=enabled)

    def allow(self, key: str) -> tuple[bool, Optional[int]]:
        now = time.time()
        self._cleanup(now)
        bucket = self._buckets.setdefault(key, deque())
        while bucket and now - bucket[0] >= self.window_seconds:
            bucket.popleft()
        if len(bucket) >= self.limit:
            retry_after = int(self.window_seconds - (now - bucket[0])) if bucket else self.window_seconds
            return False, max(1, retry_after)
        bucket.append(now)
        return True, None
