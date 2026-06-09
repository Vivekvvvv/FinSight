# -*- coding: utf-8 -*-
"""Tests for entitlements service and API."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _configure_test_storage(tmp_path: Path) -> None:
    """Redirect entitlements service to a tmp file & reset singleton."""
    from backend.services import entitlements as ent_module

    ent_module.PLANS_FILE = tmp_path / "user_plans_test.json"
    ent_module.reset_entitlements_service_for_tests()


def test_default_plan_is_free(tmp_path):
    _configure_test_storage(tmp_path)
    from backend.services.entitlements import get_entitlements_service

    service = get_entitlements_service()
    assert service.get_plan("alice") == "free"
    ent = service.get_entitlements("alice")
    assert ent["plan"] == "free"
    assert ent["features"]["deep_research"] is False
    assert ent["limits"]["max_watchlist"] == 5


def test_admin_role_forces_admin_plan(tmp_path):
    _configure_test_storage(tmp_path)
    from backend.services.entitlements import get_entitlements_service

    service = get_entitlements_service()
    ent = service.get_entitlements("ops", role="admin")
    assert ent["plan"] == "admin"
    assert ent["is_admin"] is True
    assert ent["features"]["rag_inspector"] is True
    assert ent["limits"]["max_alerts"] == -1


def test_set_plan_normalizes_invalid(tmp_path):
    _configure_test_storage(tmp_path)
    from backend.services.entitlements import get_entitlements_service

    service = get_entitlements_service()
    assert service.set_plan("bob", "PRO") == "pro"
    assert service.get_plan("bob") == "pro"
    assert service.set_plan("bob", "garbage") == "free"
    assert service.get_plan("bob") == "free"


def test_check_quota_enforces_limit(tmp_path):
    _configure_test_storage(tmp_path)
    from backend.services.entitlements import get_entitlements_service

    service = get_entitlements_service()
    service.set_plan("carol", "free")

    ok = service.check_quota("carol", "max_watchlist", 3)
    assert ok["allowed"] is True
    assert ok["remaining"] == 2

    blocked = service.check_quota("carol", "max_watchlist", 5)
    assert blocked["allowed"] is False
    assert blocked["remaining"] == 0

    service.set_plan("carol", "admin")
    unlimited = service.check_quota("carol", "max_watchlist", 999)
    assert unlimited["allowed"] is True
    assert unlimited["limit"] == -1


def test_entitlements_persist_across_instances(tmp_path):
    _configure_test_storage(tmp_path)
    from backend.services import entitlements as ent_module
    from backend.services.entitlements import get_entitlements_service

    get_entitlements_service().set_plan("dave", "team")

    # Reset singleton — should re-read from disk
    ent_module.reset_entitlements_service_for_tests()
    assert get_entitlements_service().get_plan("dave") == "team"


def test_api_me_entitlements_dev_mode(tmp_path, monkeypatch):
    _configure_test_storage(tmp_path)
    monkeypatch.setenv("DEV_MODE", "true")
    monkeypatch.setenv("DEV_USER_ID", "dev_tester")

    from backend.api.main import app

    with TestClient(app) as client:
        resp = client.get("/api/me/entitlements")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        # dev_principal has role=admin -> plan=admin
        assert data["plan"] == "admin"
        assert data["features"]["dashboard"] is True
        assert data["limits"]["max_alerts"] == -1


def test_api_me_returns_current_principal(tmp_path, monkeypatch):
    _configure_test_storage(tmp_path)
    monkeypatch.setenv("DEV_MODE", "true")
    monkeypatch.setenv("DEV_USER_ID", "vue_user")
    monkeypatch.setenv("DEV_USER_EMAIL", "vue@example.invalid")

    from backend.api.main import app

    with TestClient(app) as client:
        resp = client.get("/api/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data == {
            "success": True,
            "user_id": "vue_user",
            "email": "vue@example.invalid",
            "role": "admin",
            "auth_type": "dev",
        }


def test_api_admin_set_plan(tmp_path, monkeypatch):
    _configure_test_storage(tmp_path)
    monkeypatch.setenv("DEV_MODE", "true")
    monkeypatch.setenv("DEV_USER_ID", "admin_tester")

    from backend.api.main import app

    with TestClient(app) as client:
        resp = client.post(
            "/api/admin/entitlements/plan",
            json={"user_id": "user_42", "plan": "pro", "source": "test"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["plan"] == "pro"

        # Invalid plan -> 422
        resp = client.post(
            "/api/admin/entitlements/plan",
            json={"user_id": "user_42", "plan": "platinum"},
        )
        assert resp.status_code == 422
