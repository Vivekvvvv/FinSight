# -*- coding: utf-8 -*-
from __future__ import annotations

import time

from fastapi.testclient import TestClient

from backend.api import portfolio_router as portfolio_router_module
from backend.api.main import app
from backend.services import portfolio_store


def test_portfolio_summary_times_out_slow_quote(monkeypatch):
    """组合页不能被单个慢行情源拖死。"""
    session_id = "public:anonymous:portfolio-timeout-test"
    portfolio_store.remove_position(session_id, "SLOW")
    portfolio_store.update_position(
        session_id=session_id,
        ticker="SLOW",
        shares=2,
        avg_cost=10,
        name="Slow Quote",
    )

    def slow_quote(_ticker: str, _get_stock_price=None):
        time.sleep(1)
        return {"price": 99, "source": "test"}, None

    monkeypatch.setenv("FINSIGHT_PORTFOLIO_QUOTE_TIMEOUT_SECONDS", "0.05")
    monkeypatch.setattr(portfolio_router_module, "resolve_live_quote", slow_quote)

    with TestClient(app) as client:
        started = time.perf_counter()
        response = client.get("/api/portfolio/summary", params={"session_id": session_id})
        elapsed = time.perf_counter() - started

    portfolio_store.remove_position(session_id, "SLOW")

    assert response.status_code == 200
    payload = response.json()
    assert elapsed < 0.5
    assert payload["success"] is True
    assert payload["priced_count"] == 0
    assert payload["total_value"] == 20
    assert payload["positions"][0]["price_source"] == "avg_cost_fallback"
