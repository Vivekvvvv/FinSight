# -*- coding: utf-8 -*-
"""R68：晨报兜底路径不得把上游缓存/延迟报价统称“实时报价”。

``parse_quote_payload`` 只保留价格字段，上游载荷里的 ``freshness_status``
被丢掉；兜底 brief 于是对缓存价也写“其中 N 只获取到实时报价”。盘前/盘后
拉到的旧价会被用户当成当前价。
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.api.morning_brief_router as morning_brief_module
from backend.api.morning_brief_router import MorningBriefRouterDeps, create_morning_brief_router
from backend.dashboard.cache import DashboardCache
from backend.security.auth import Principal, get_current_user


def _brief(monkeypatch, price_payloads: dict[str, object]) -> dict:
    monkeypatch.setattr(morning_brief_module, "dashboard_cache", DashboardCache())
    app = FastAPI()
    app.include_router(
        create_morning_brief_router(
            MorningBriefRouterDeps(
                resolve_thread_id=lambda session_id: str(session_id),
                get_portfolio_positions=lambda _session_id: [],
                get_stock_price=lambda ticker: price_payloads[ticker],
                get_company_news=lambda _ticker, _limit: [],
            )
        )
    )
    app.dependency_overrides[get_current_user] = lambda: Principal(
        user_id="alice", role="user", auth_type="api_key",
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/morning-brief/generate",
            json={"session_id": "private:alice:default", "tickers": sorted(price_payloads)},
        )
    assert response.status_code == 200, response.text
    return response.json()["brief"]


def test_cached_quote_is_not_reported_as_realtime(monkeypatch):
    brief = _brief(
        monkeypatch,
        {
            "AAPL": {
                "ticker": "AAPL",
                "price": 100.0,
                "change": 1.0,
                "change_percent": 1.0,
                "freshness_status": "cached",
            },
        },
    )

    assert brief["freshness_status"] == "cached"
    assert brief["live_price_count"] == 0
    assert brief["highlights"][0]["freshness_status"] == "cached"
    assert "实时报价" not in brief["summary"]
    assert "缓存/延迟" in brief["summary"]


def test_nested_data_freshness_is_honored(monkeypatch):
    brief = _brief(
        monkeypatch,
        {
            "AAPL": {
                "data": {
                    "price": 100.0,
                    "change_percent": 1.0,
                    "freshness_status": "delayed_15min",
                },
            },
        },
    )

    assert brief["highlights"][0]["freshness_status"] == "delayed_15min"
    assert brief["freshness_status"] == "cached"


def test_live_quote_still_says_realtime(monkeypatch):
    brief = _brief(
        monkeypatch,
        {
            "AAPL": {
                "ticker": "AAPL",
                "price": 100.0,
                "change_percent": 1.0,
                "freshness_status": "live",
            },
        },
    )

    assert brief["freshness_status"] == "live"
    assert brief["live_price_count"] == 1
    assert "获取到实时报价" in brief["summary"]


def test_payload_without_declared_freshness_keeps_old_behavior(monkeypatch):
    brief = _brief(
        monkeypatch, {"AAPL": {"ticker": "AAPL", "price": 100.0, "change_percent": 1.0}}
    )

    assert brief["highlights"][0]["freshness_status"] == "live"
    assert brief["freshness_status"] == "live"


def test_missing_price_has_no_freshness_label(monkeypatch):
    brief = _brief(monkeypatch, {"AAPL": None})

    assert brief["highlights"][0]["freshness_status"] is None
    assert brief["freshness_status"] == "unknown"
    assert brief["live_price_count"] == 0


# ── Graph Pipeline 路径（synthesize_brief）同样不得把缓存价说成实时 ──


def _graph_brief(price_outputs: dict[str, object]) -> dict:
    from backend.graph.nodes.synthesize import _synthesize_morning_brief_data

    tickers = list(price_outputs)
    steps = [
        {"id": f"s{i}", "name": "get_stock_price", "inputs": {"ticker": t}}
        for i, t in enumerate(tickers)
    ]
    step_results = {
        f"s{i}": {"output": price_outputs[t]} for i, t in enumerate(tickers)
    }
    state = {
        "subject": {"tickers": tickers},
        "plan_ir": {"steps": steps},
        "artifacts": {"step_results": step_results},
    }
    return _synthesize_morning_brief_data(state)["brief_data"]


def test_graph_brief_cached_quote_is_not_reported_as_realtime():
    brief = _graph_brief(
        {
            "AAPL": {
                "price": 100.0,
                "change": 1.0,
                "change_percent": 1.0,
                "freshness_status": "cached",
            },
        }
    )

    assert brief["highlights"][0]["freshness_status"] == "cached"
    assert brief["freshness_status"] == "cached"
    assert brief["live_price_count"] == 0
    assert "实时报价" not in brief["summary"]
    assert "缓存/延迟" in brief["summary"]


def test_graph_brief_nested_data_freshness_is_honored():
    brief = _graph_brief(
        {"AAPL": {"data": {"price": 100.0, "freshness_status": "delayed_15min"}}}
    )

    assert brief["highlights"][0]["freshness_status"] == "delayed_15min"


def test_graph_brief_live_quote_still_says_realtime():
    brief = _graph_brief(
        {"AAPL": {"price": 100.0, "change_percent": 1.0, "freshness_status": "live"}}
    )

    assert brief["freshness_status"] == "live"
    assert brief["live_price_count"] == 1
    assert "获取到实时报价" in brief["summary"]


def test_graph_brief_missing_price_has_no_freshness_label():
    brief = _graph_brief({"AAPL": None})

    assert brief["highlights"][0]["freshness_status"] is None
    assert brief["freshness_status"] == "unknown"
