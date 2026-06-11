# -*- coding: utf-8 -*-
"""Demo Mode smoke tests."""

from fastapi.testclient import TestClient

from backend.api.demo_router import demo_router
from backend.demo_mode import (
    demo_notes,
    demo_portfolio_summary,
    demo_reports,
    demo_status,
    demo_timeline,
    demo_today_workspace,
)


def test_demo_status_reports_mode_and_missing_services(monkeypatch):
    monkeypatch.setenv("FINSIGHT_DEMO_MODE", "true")
    monkeypatch.delenv("FMP_API_KEY", raising=False)

    status = demo_status()

    assert status["success"] is True
    assert status["demo_mode"] is True
    assert status["data_source"] == "demo"
    assert "FMP_API_KEY" in status["missing_services"]


def test_demo_status_api():
    app = __import__("fastapi").FastAPI()
    app.include_router(demo_router)

    with TestClient(app) as client:
        response = client.get("/api/demo/status")

    assert response.status_code == 200
    assert response.json()["success"] is True


def test_demo_core_payloads_are_non_empty():
    session_id = "public:demo:thread"

    portfolio = demo_portfolio_summary(session_id)
    today = demo_today_workspace(session_id)
    reports = demo_reports(session_id)
    notes = demo_notes(session_id, "demo_user")
    timeline = demo_timeline("AAPL", session_id)

    assert portfolio["count"] >= 2
    assert today["portfolio_snapshot"]["position_count"] >= 2
    assert len(reports) >= 2
    assert len(notes) >= 2
    assert len(timeline) >= 2
    assert today["freshness_status"] == "demo"
