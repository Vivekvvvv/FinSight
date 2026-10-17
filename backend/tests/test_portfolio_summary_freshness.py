# -*- coding: utf-8 -*-
"""组合摘要必须把上游报价自带的 freshness 透给前端。"""
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.api import portfolio_router as portfolio_router_module
from backend.api.main import app
from backend.services import portfolio_store


def test_portfolio_summary_exposes_upstream_cached_quote_freshness(monkeypatch):
    session_id = "public:anonymous:portfolio-freshness-test"
    portfolio_store.remove_position(session_id, "CACHEDY")
    portfolio_store.update_position(
        session_id=session_id,
        ticker="CACHEDY",
        shares=2,
        avg_cost=10,
    )

    def cached_quote(_ticker: str, _get_stock_price=None):
        return {
            "price": 12.0,
            "change": 0.5,
            "change_percent": 4.3,
            "source": "tools_bridge",
            "freshness_status": "cached",
            "fallback_level": 2,
        }, None

    monkeypatch.setattr(portfolio_router_module, "resolve_live_quote", cached_quote)

    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/portfolio/summary",
                params={"session_id": session_id},
            )
    finally:
        portfolio_store.remove_position(session_id, "CACHEDY")

    assert response.status_code == 200
    position = response.json()["positions"][0]
    # price_source 仍是 tools_bridge，前端只按它推断会标成 live
    assert position["price_source"] == "tools_bridge"
    assert position["price_freshness"] == "cached"
    assert position["price_fallback_level"] == 2
