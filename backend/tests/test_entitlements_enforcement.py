# -*- coding: utf-8 -*-
"""Tests for entitlements enforcement helpers + endpoint-level plan gating."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _configure_storage(tmp_path: Path) -> None:
    from backend.services import entitlements as ent_module

    ent_module.PLANS_FILE = tmp_path / "user_plans_enforcement.json"
    ent_module.reset_entitlements_service_for_tests()


# ── unit tests for helpers ─────────────────────────────────────


def test_enforce_feature_blocks_free_plan(tmp_path):
    _configure_storage(tmp_path)
    from backend.security.auth import Principal
    from backend.services.entitlements import enforce_feature, get_entitlements_service

    get_entitlements_service().set_plan("u1", "free")
    p = Principal(user_id="u1", email=None, role="user", auth_type="api_key")

    with pytest.raises(HTTPException) as exc_info:
        enforce_feature(p, "deep_research")

    assert exc_info.value.status_code == 403
    detail = exc_info.value.detail
    assert detail["code"] == "plan_feature_required"
    assert detail["feature"] == "deep_research"
    assert detail["plan"] == "free"


def test_enforce_feature_allows_pro_plan(tmp_path):
    _configure_storage(tmp_path)
    from backend.security.auth import Principal
    from backend.services.entitlements import enforce_feature, get_entitlements_service

    get_entitlements_service().set_plan("u2", "pro")
    p = Principal(user_id="u2", email=None, role="user", auth_type="api_key")

    # Should not raise.
    enforce_feature(p, "deep_research")
    enforce_feature(p, "export_pdf")
    enforce_feature(p, "backtest")


def test_enforce_feature_admin_role_bypasses_plan_file(tmp_path):
    _configure_storage(tmp_path)
    from backend.security.auth import Principal
    from backend.services.entitlements import enforce_feature

    # Admin role wins even without an explicit plan record.
    p = Principal(user_id="ops", email=None, role="admin", auth_type="api_key")
    enforce_feature(p, "rag_inspector")
    enforce_feature(p, "deep_research")


def test_enforce_feature_anonymous_treated_as_free(tmp_path):
    _configure_storage(tmp_path)
    from backend.services.entitlements import enforce_feature

    with pytest.raises(HTTPException) as exc_info:
        enforce_feature(None, "deep_research")
    assert exc_info.value.status_code == 403


def test_enforce_quota_blocks_when_over_limit(tmp_path):
    _configure_storage(tmp_path)
    from backend.security.auth import Principal
    from backend.services.entitlements import enforce_quota, get_entitlements_service

    get_entitlements_service().set_plan("u3", "free")
    p = Principal(user_id="u3", email=None, role="user", auth_type="api_key")
    # Free max_alerts = 3
    enforce_quota(p, "max_alerts", current_count=2)  # ok, 2<3
    with pytest.raises(HTTPException) as exc_info:
        enforce_quota(p, "max_alerts", current_count=3)
    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["code"] == "plan_quota_exceeded"


def test_enforce_quota_unlimited_for_admin(tmp_path):
    _configure_storage(tmp_path)
    from backend.security.auth import Principal
    from backend.services.entitlements import enforce_quota

    p = Principal(user_id="ops", email=None, role="admin", auth_type="api_key")
    decision = enforce_quota(p, "max_alerts", current_count=99999)
    assert decision["limit"] == -1
    assert decision["remaining"] == -1


# ── endpoint-level integration tests ───────────────────────────


def test_export_pdf_blocked_for_free_user(tmp_path, monkeypatch):
    """Free plan cannot call /api/export/pdf — returns 403 with plan_feature_required."""
    _configure_storage(tmp_path)
    # DEV_MODE=true keeps lifespan happy; monkeypatch dev_principal so middleware
    # injects a non-admin free-plan user instead of the default admin principal.
    monkeypatch.setenv("DEV_MODE", "true")

    from backend.api import main as main_module
    from backend.security.auth import Principal
    from backend.services.entitlements import get_entitlements_service

    get_entitlements_service().set_plan("free_user", "free")

    fake_principal = Principal(user_id="free_user", email="f@x", role="user", auth_type="dev")
    monkeypatch.setattr(main_module, "dev_principal", lambda: fake_principal)

    from backend.api.main import app

    with TestClient(app) as client:
        resp = client.post(
            "/api/export/pdf",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
        assert resp.status_code == 403, resp.text
        body = resp.json()
        detail = body.get("detail", {})
        assert detail.get("code") == "plan_feature_required"
        assert detail.get("feature") == "export_pdf"


def test_export_pdf_allowed_for_pro_user(tmp_path, monkeypatch):
    """Pro plan passes the gate (downstream may fail for other reasons, but never 403 plan_feature_required)."""
    _configure_storage(tmp_path)
    monkeypatch.setenv("DEV_MODE", "true")

    from backend.api import main as main_module
    from backend.security.auth import Principal
    from backend.services.entitlements import get_entitlements_service

    get_entitlements_service().set_plan("pro_user", "pro")
    fake_principal = Principal(user_id="pro_user", email="p@x", role="user", auth_type="dev")
    monkeypatch.setattr(main_module, "dev_principal", lambda: fake_principal)

    from backend.api.main import app

    with TestClient(app) as client:
        resp = client.post(
            "/api/export/pdf",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
        if resp.status_code == 403:
            assert resp.json().get("detail", {}).get("code") != "plan_feature_required"


def test_chat_supervisor_investment_report_blocked_for_free(tmp_path, monkeypatch):
    """Free plan cannot generate investment_report via /chat/supervisor."""
    _configure_storage(tmp_path)
    monkeypatch.setenv("DEV_MODE", "true")

    from backend.api import main as main_module
    from backend.security.auth import Principal
    from backend.services.entitlements import get_entitlements_service

    get_entitlements_service().set_plan("free_rep", "free")
    fake_principal = Principal(user_id="free_rep", email="fr@x", role="user", auth_type="dev")
    monkeypatch.setattr(main_module, "dev_principal", lambda: fake_principal)

    from backend.api.main import app

    with TestClient(app) as client:
        resp = client.post(
            "/chat/supervisor",
            json={
                "query": "Generate full report on AAPL",
                "session_id": "private:free_rep:default",
                "options": {"output_mode": "investment_report"},
            },
        )
        assert resp.status_code == 403
        detail = resp.json().get("detail", {})
        assert detail.get("code") == "plan_feature_required"
        assert detail.get("feature") == "deep_research"
