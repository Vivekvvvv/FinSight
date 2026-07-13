# -*- coding: utf-8 -*-
"""R68 回归：principal_from_api_key 未配 ADMIN_KEYS 时默认 user（fail-close）。

旧实现 `role = "admin" if not admin_keys or api_key in admin_keys else "user"`
在未配 API_AUTH_ADMIN_KEYS 时把所有 API_AUTH_KEYS 的 key 都当 admin
（fail-open）——下游 consumer key 意外获得 admin，可访问管理端点。
"""
from __future__ import annotations

from backend.security.auth import principal_from_api_key


def test_defaults_to_user_without_admin_keys(monkeypatch):
    monkeypatch.delenv("API_AUTH_PRINCIPALS", raising=False)
    monkeypatch.delenv("API_AUTH_ADMIN_KEYS", raising=False)
    p = principal_from_api_key("consumer-key")
    assert p.role == "user"
    assert p.is_admin is False


def test_admin_only_when_key_in_admin_keys(monkeypatch):
    monkeypatch.delenv("API_AUTH_PRINCIPALS", raising=False)
    monkeypatch.setenv("API_AUTH_ADMIN_KEYS", "ops-key, admin-key")
    assert principal_from_api_key("admin-key").role == "admin"
    assert principal_from_api_key("ops-key").role == "admin"
    # 不在 admin 列表的 key 仍是 user
    assert principal_from_api_key("consumer-key").role == "user"


def test_explicit_principals_mapping_still_wins(monkeypatch):
    # 显式 PRINCIPALS 映射优先，不受 fallback 改动影响
    monkeypatch.setenv("API_AUTH_PRINCIPALS", '{"k1":{"user_id":"alice","role":"user"}}')
    monkeypatch.delenv("API_AUTH_ADMIN_KEYS", raising=False)
    p = principal_from_api_key("k1")
    assert p.user_id == "alice"
    assert p.role == "user"
