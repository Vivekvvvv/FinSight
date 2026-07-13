# -*- coding: utf-8 -*-
"""认证主体与安全模式工具。"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


def env_bool(key: str, default: str = "false") -> bool:
    return str(os.getenv(key, default)).strip().lower() in {"1", "true", "yes", "on"}


def is_dev_mode() -> bool:
    return env_bool("DEV_MODE", "false")


@dataclass(frozen=True)
class Principal:
    user_id: str
    email: str | None = None
    role: str = "user"
    auth_type: str = "unknown"

    @property
    def is_admin(self) -> bool:
        return self.role in {"admin", "internal"}

    @property
    def session_id(self) -> str:
        return f"private:{self.user_id}:default"


def dev_principal(user_id: str | None = None, email: str | None = None) -> Principal:
    resolved_user = (user_id or os.getenv("DEV_USER_ID") or "default_user").strip()
    resolved_email = (email or os.getenv("DEV_USER_EMAIL") or "dev@example.invalid").strip()
    return Principal(user_id=resolved_user, email=resolved_email, role="admin", auth_type="dev")


def guest_principal() -> Principal:
    """游客身份"""
    return Principal(user_id="guest:anonymous", email=None, role="guest", auth_type="anonymous")


def api_key_fingerprint(api_key: str) -> str:
    digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]
    return f"api_{digest}"


def principal_from_api_key(api_key: str) -> Principal:
    """把内部 API key 映射为最小认证主体。

    可用 API_AUTH_PRINCIPALS 配置精确映射：
    {"key": {"user_id": "ops", "email": "ops@example.invalid", "role": "admin"}}
    """

    mappings_raw = str(os.getenv("API_AUTH_PRINCIPALS") or "").strip()
    if mappings_raw:
        try:
            mappings = json.loads(mappings_raw)
            row = mappings.get(api_key) if isinstance(mappings, dict) else None
            if isinstance(row, dict):
                return Principal(
                    user_id=str(row.get("user_id") or api_key_fingerprint(api_key)),
                    email=str(row.get("email") or "").strip() or None,
                    role=str(row.get("role") or "user").strip().lower() or "user",
                    auth_type="api_key",
                )
        except Exception:
            logger.warning("API_AUTH_PRINCIPALS is invalid JSON; falling back to hashed API key principal")

    admin_keys = {item.strip() for item in str(os.getenv("API_AUTH_ADMIN_KEYS") or "").split(",") if item.strip()}
    # fail-close：未配 API_AUTH_ADMIN_KEYS 时默认 user，而非把所有 API_AUTH_KEYS
    # 里的 key 都当 admin。原 `not admin_keys or ...` 是 fail-open：给下游
    # consumer 发的 key 会意外获得 admin，可访问 config/entitlements/subscription
    # 管理端点。需要 admin 的部署须显式配 API_AUTH_ADMIN_KEYS 或
    # API_AUTH_PRINCIPALS（R68）。
    role = "admin" if api_key in admin_keys else "user"
    return Principal(
        user_id=os.getenv("API_AUTH_DEFAULT_USER_ID") or api_key_fingerprint(api_key),
        email=os.getenv("API_AUTH_DEFAULT_EMAIL") or "api-user@example.invalid",
        role=role,
        auth_type="api_key",
    )


def get_current_user(request: Request) -> Principal:
    principal = getattr(request.state, "principal", None)
    if isinstance(principal, Principal):
        return principal
    if is_dev_mode():
        principal = dev_principal()
        request.state.principal = principal
        return principal
    raise HTTPException(status_code=401, detail="Authentication required")


def require_admin_principal(request: Request) -> Principal:
    principal = get_current_user(request)
    if not principal.is_admin:
        raise HTTPException(status_code=403, detail="Admin role required")
    return principal


def require_matching_identity(
    *,
    principal: Principal,
    provided: str | None,
    expected: str,
    field_name: str,
) -> None:
    supplied = str(provided or "").strip()
    if not supplied:
        return
    if principal.auth_type == "dev":
        return
    if supplied != expected:
        raise HTTPException(status_code=403, detail=f"{field_name} does not match authenticated principal")
