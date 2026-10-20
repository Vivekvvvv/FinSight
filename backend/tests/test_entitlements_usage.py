# -*- coding: utf-8 -*-
"""Tests for entitlements usage view (今日报告/订阅/持仓计数 + /api/me/usage)."""

from __future__ import annotations

import os
import sys
import logging
from pathlib import Path

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _configure_storage(tmp_path: Path) -> None:
    from backend.services import entitlements as ent_module

    ent_module.PLANS_FILE = tmp_path / "user_plans_usage.json"
    ent_module.reset_entitlements_service_for_tests()


def test_build_usage_view_returns_all_quota_keys(tmp_path):
    _configure_storage(tmp_path)
    from backend.services.entitlements import build_usage_view, get_entitlements_service

    get_entitlements_service().set_plan("u_usage", "free")
    usage = build_usage_view("u_usage")

    assert set(usage.keys()) == {
        "max_reports_per_day",
        "max_alerts",
        "max_portfolio_positions",
        "max_watchlist",
        "max_deep_research_per_day",
    }
    for key, entry in usage.items():
        assert "used" in entry
        assert "limit" in entry
        assert "remaining" in entry
        assert "percent" in entry
        assert "allowed" in entry
        assert "plan" in entry
        assert entry["plan"] == "free"


def test_usage_admin_unlimited(tmp_path):
    _configure_storage(tmp_path)
    from backend.services.entitlements import build_usage_view

    # admin role -> all quotas should report limit=-1, remaining=-1
    usage = build_usage_view("ops", role="admin")
    assert all(entry["plan"] == "admin" for entry in usage.values())
    assert all(entry["limit"] == -1 for entry in usage.values())
    assert all(entry["remaining"] == -1 for entry in usage.values())


def test_usage_counts_actual_subscriptions(tmp_path, monkeypatch):
    """订阅服务返回 2 条 -> max_alerts.used 应该为 2。"""
    _configure_storage(tmp_path)

    from backend.services import subscription_service as subs

    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", tmp_path / "subs.json")
    monkeypatch.setattr(subs, "_subscription_service", None)

    service = subs.get_subscription_service()
    service.subscribe("u_alerts@example.invalid", "AAPL", alert_types=["price_change"])
    service.subscribe("u_alerts@example.invalid", "MSFT", alert_types=["news"])

    from backend.services.entitlements import build_usage_view, get_entitlements_service

    get_entitlements_service().set_plan("u_alerts", "free")
    usage = build_usage_view("u_alerts", email="u_alerts@example.invalid")
    assert usage["max_alerts"]["used"] == 2
    assert usage["max_alerts"]["remaining"] == 1  # free limit=3
    assert usage["max_alerts"]["percent"] == 67


def test_api_me_entitlements_returns_usage(tmp_path, monkeypatch):
    """GET /api/me/entitlements must include `usage` dict with all quota keys."""
    _configure_storage(tmp_path)
    monkeypatch.setenv("DEV_MODE", "true")

    from backend.api import main as main_module
    from backend.security.auth import Principal

    fake = Principal(user_id="api_user", email="x@x", role="user", auth_type="dev")
    monkeypatch.setattr(main_module, "dev_principal", lambda: fake)

    from backend.api.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        resp = client.get("/api/me/entitlements")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["success"] is True
        assert data["plan"] == "free"
        assert "usage" in data
        assert "max_alerts" in data["usage"]
        assert data["usage"]["max_alerts"]["limit"] == 3


def test_api_me_usage_endpoint(tmp_path, monkeypatch):
    _configure_storage(tmp_path)
    monkeypatch.setenv("DEV_MODE", "true")

    from backend.api import main as main_module
    from backend.security.auth import Principal

    fake = Principal(user_id="usage_user", email="u@x", role="admin", auth_type="dev")
    monkeypatch.setattr(main_module, "dev_principal", lambda: fake)

    from backend.api.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        resp = client.get("/api/me/usage")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["success"] is True
        assert data["plan"] == "admin"
        assert "max_reports_per_day" in data["usage"]
        assert data["usage"]["max_reports_per_day"]["plan"] == "admin"
        assert data["usage"]["max_reports_per_day"]["limit"] == -1


def test_api_plans_returns_all_tiers(tmp_path, monkeypatch):
    _configure_storage(tmp_path)
    monkeypatch.setenv("DEV_MODE", "true")

    from backend.api.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        resp = client.get("/api/plans")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        plan_ids = [p["id"] for p in data["plans"]]
        assert plan_ids == ["free", "pro", "team", "admin"]
        # Pro plan must have deep_research feature & export_pdf feature.
        pro = next(p for p in data["plans"] if p["id"] == "pro")
        assert pro["features"]["deep_research"] is True
        assert pro["features"]["export_pdf"] is True
        # Admin plan has unlimited alerts.
        admin_plan = next(p for p in data["plans"] if p["id"] == "admin")
        assert admin_plan["limits"]["max_alerts"] == -1


def test_count_reports_since_returns_zero_when_empty(tmp_path, monkeypatch):
    """report_index 空表时 count_reports_since 必须返回 0,不抛异常。"""
    _configure_storage(tmp_path)
    monkeypatch.setenv("REPORT_INDEX_SQLITE_PATH", str(tmp_path / "report_index_test.sqlite"))
    # Reset cached store
    from backend.services import report_index as ri_module
    ri_module._REPORT_INDEX_STORE = None

    store = ri_module.get_report_index_store()
    count = store.count_reports_since(
        session_id="private:nobody:default",
        since="2026-05-18T00:00:00+00:00",
    )
    assert count == 0


def test_usage_fallback_logs_do_not_expose_exception_details(
    tmp_path, monkeypatch, caplog
):
    _configure_storage(tmp_path)
    from backend.services import portfolio_store, report_index, subscription_service
    from backend.services.entitlements import build_usage_view

    def fail(*_args, **_kwargs):
        raise RuntimeError("private usage storage detail")

    monkeypatch.setattr(report_index, "get_report_index_store", fail)
    monkeypatch.setattr(subscription_service, "get_subscription_service", fail)
    monkeypatch.setattr(portfolio_store, "get_positions", fail)

    with caplog.at_level(logging.ERROR, logger="backend.services.entitlements"):
        usage = build_usage_view("usage_error_user")

    assert usage["max_reports_per_day"]["used"] == 0
    assert usage["max_alerts"]["used"] == 0
    assert usage["max_portfolio_positions"]["used"] == 0
    assert "private usage storage detail" not in caplog.text
    assert "build_usage_view: count_reports_since failed; fallback 0" in caplog.text
    assert "build_usage_view: count subscriptions failed; fallback 0" in caplog.text
    assert "build_usage_view: count portfolio positions failed; fallback 0" in caplog.text


def test_usage_fallback_zero_is_marked_as_not_measured(tmp_path, monkeypatch):
    """计数失败回退的 0 和"用户确实没消耗"在结构上同形：额度条两种情况下都
    显示满血，用户以为配额没用、管理员以为盘子里没东西。降级必须显式标出
    （项目规则 2、finsight-silent-success-forbidden）。"""
    _configure_storage(tmp_path)
    from backend.services import portfolio_store, report_index, subscription_service
    from backend.services.entitlements import build_usage_view

    def fail(*_args, **_kwargs):
        raise RuntimeError("private usage storage detail")

    monkeypatch.setattr(report_index, "get_report_index_store", fail)
    monkeypatch.setattr(subscription_service, "get_subscription_service", fail)
    monkeypatch.setattr(portfolio_store, "get_positions", fail)

    usage = build_usage_view("usage_degraded_user")

    for key in ("max_reports_per_day", "max_alerts", "max_portfolio_positions"):
        assert usage[key]["used"] == 0
        assert usage[key]["fallback_reason"] == "usage_count_unavailable"


def test_real_zero_usage_is_not_marked_degraded(tmp_path, monkeypatch):
    """真·零使用（存储可用、计数就是 0）不能被降级标记污染。"""
    _configure_storage(tmp_path)
    from backend.services import portfolio_store, report_index, subscription_service
    from backend.services.entitlements import build_usage_view

    class _ReportStore:
        def count_reports_since(self, **_kwargs):
            return 0

    class _SubService:
        def get_subscriptions(self, **_kwargs):
            return []

    monkeypatch.setattr(report_index, "get_report_index_store", lambda: _ReportStore())
    monkeypatch.setattr(subscription_service, "get_subscription_service", lambda: _SubService())
    monkeypatch.setattr(portfolio_store, "get_positions", lambda _sid, _diag=None: [])

    usage = build_usage_view("usage_clean_user")

    for key in ("max_reports_per_day", "max_alerts", "max_portfolio_positions"):
        assert usage[key]["used"] == 0
        assert "fallback_reason" not in usage[key]


def test_usage_counts_unreadable_positions_instead_of_undercounting(tmp_path, monkeypatch):
    """坏持仓行被 get_positions 跳过时，不能少报 used：额度条会显示"还没满"，
    用户/管理员据此以为配额没被消耗（项目规则 2、finsight-silent-success-forbidden）。"""
    _configure_storage(tmp_path)
    from backend.services import portfolio_store
    from backend.services.entitlements import build_usage_view

    def _get_positions(_session_id, diagnostics=None):
        if diagnostics is not None:
            diagnostics["invalid_positions"] = ["BADROW"]
        return [{"ticker": "AAPL", "shares": 10, "avg_cost": 150.0}]

    monkeypatch.setattr(portfolio_store, "get_positions", _get_positions)

    usage = build_usage_view("usage_partial_user")

    entry = usage["max_portfolio_positions"]
    # 1 行可解析 + 1 行坏行：两行都占额度。
    assert entry["used"] == 2
    assert entry["fallback_reason"] == "usage_count_partial"


def test_usage_without_invalid_positions_is_not_marked_partial(tmp_path, monkeypatch):
    """只有能解析的持仓时不该带 usage_count_partial。"""
    _configure_storage(tmp_path)
    from backend.services import portfolio_store
    from backend.services.entitlements import build_usage_view

    def _get_positions(_session_id, diagnostics=None):
        return [{"ticker": "AAPL", "shares": 10, "avg_cost": 150.0}]

    monkeypatch.setattr(portfolio_store, "get_positions", _get_positions)

    usage = build_usage_view("usage_clean_positions_user")

    entry = usage["max_portfolio_positions"]
    assert entry["used"] == 1
    assert "fallback_reason" not in entry
