# -*- coding: utf-8 -*-
"""Portfolio API validation tests for cost-basis and bulk import payloads."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_update_position_rejects_negative_avg_cost(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")
    from backend.api import main

    monkeypatch.setattr(main, "_rate_limiter", main.SimpleRateLimiter(limit_per_window=100, window_seconds=60, enabled=False))

    with TestClient(main.app) as client:
        resp = client.put(
            "/api/portfolio/positions/AAPL",
            params={"session_id": "private:default_user:default"},
            json={"shares": 10, "avg_cost": -1},
        )

    assert resp.status_code == 422


def test_bulk_sync_rejects_negative_cost_and_shares(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")
    from backend.api import main

    monkeypatch.setattr(main, "_rate_limiter", main.SimpleRateLimiter(limit_per_window=100, window_seconds=60, enabled=False))

    with TestClient(main.app) as client:
        cost_resp = client.post(
            "/api/portfolio/positions",
            json={
                "session_id": "private:default_user:default",
                "positions": [{"ticker": "AAPL", "shares": 1, "avg_cost": -10}],
            },
        )
        shares_resp = client.post(
            "/api/portfolio/positions",
            json={
                "session_id": "private:default_user:default",
                "positions": [{"ticker": "MSFT", "shares": -1, "avg_cost": 300}],
            },
        )

    assert cost_resp.status_code == 422
    assert shares_resp.status_code == 422
