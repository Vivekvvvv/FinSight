# -*- coding: utf-8 -*-
"""
P0 稳定性回归测试：健康检查与基本请求校验。

目标：
- / 与 /health 端点始终可用，用于监控与存活检查；
- /chat/supervisor 在收到空 query 时由 Pydantic 校验层直接返回 422，
  避免空请求进入主链路。
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.api.main import app  # noqa: E402
from backend.api import screener_router as screener_router_module  # noqa: E402


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_root_health_endpoint(client):
    """根路径应返回 healthy 状态和时间戳。"""
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "healthy"
    assert "timestamp" in data
    assert "message" in data


def test_health_endpoint(client):
    """/health 端点应只返回公开存活信息。"""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "ok"
    assert "version" in data
    assert "uptime_seconds" in data
    assert "components" not in data
    assert "recent_runs" not in data
    assert "query_text" not in str(data)
    assert "timestamp" in data


def test_chat_empty_query_validation(client):
    """
    空 query 应在进入处理函数前被 Pydantic 拦截，返回 422。
    这样可以避免空请求进入主链路，提升稳健性。
    """
    resp = client.post("/chat/supervisor", json={"query": ""})
    assert resp.status_code == 422


def test_legacy_chat_endpoint_removed(client):
    """旧 /chat 端点应已移除，返回 404。"""
    resp = client.post("/chat", json={"query": "AAPL 现在多少钱"})
    assert resp.status_code == 404


def test_legacy_demo_status_has_timestamp(client):
    """旧 Demo 状态接口也应携带 as_of，方便前端说明状态更新时间。"""
    resp = client.get("/api/demo/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("success") is True
    assert data.get("as_of")
    assert isinstance(data.get("missing_services"), list)


def test_research_workspace_core_api_smoke(client, monkeypatch):
    """核心页面依赖的后端接口应在无外部网络时保持稳定响应。"""
    fake_items = [
        {
            "symbol": "600519.SS",
            "name": "Kweichow Moutai Co., Ltd.",
            "country": "CN",
            "exchange": "Shanghai",
            "price": 1702.0,
            "market_cap": 2_138_000_000_000,
        }
    ]

    def _fake_screen_stocks(**kwargs):
        return {
            "success": True,
            "market": kwargs.get("market", "CN"),
            "filters": kwargs.get("filters") or {},
            "sort": {"by": kwargs.get("sort_by"), "order": kwargs.get("sort_order")},
            "items": fake_items,
            "results": fake_items,
            "count": len(fake_items),
            "source": "static_market_demo",
            "warning": "demo_market_fallback",
            "capability_note": "Using built-in candidates for smoke validation.",
        }

    monkeypatch.setattr(screener_router_module, "screen_stocks", _fake_screen_stocks)

    source_resp = client.get("/api/data-sources/status")
    assert source_resp.status_code == 200
    source_data = source_resp.json()
    component_keys = {item["key"] for item in source_data.get("components", [])}
    assert {"market_us", "market_cn", "market_hk", "llm", "rag", "auth"}.issubset(component_keys)
    assert source_data.get("as_of")
    assert any("evidence" in note for note in source_data.get("notes", []))

    meta_resp = client.get("/api/screener/filters/meta")
    assert meta_resp.status_code == 200
    meta = meta_resp.json()
    assert {"US", "CN", "HK"}.issubset(set(meta.get("markets", [])))

    screener_resp = client.post(
        "/api/screener/run",
        json={"market": "CN", "filters": {}, "limit": 3, "page": 1, "sort_by": "marketCap", "sort_order": "desc"},
    )
    assert screener_resp.status_code == 200
    screener = screener_resp.json()
    assert screener.get("success") is True
    assert screener.get("source") == "static_market_demo"
    assert screener.get("warning") == "demo_market_fallback"
    assert screener.get("items", [])[0]["symbol"].endswith((".SS", ".SZ"))

    today_resp = client.get("/api/today", params={"session_id": "public:anonymous:smoke", "user_id": "default_user"})
    assert today_resp.status_code == 200
    today = today_resp.json()
    assert today.get("success") is True
    assert today.get("as_of")
    assert isinstance(today.get("portfolio_snapshot"), dict)
    assert isinstance(today.get("next_actions"), list)

    portfolio_resp = client.get("/api/portfolio/summary", params={"session_id": "public:anonymous:smoke"})
    assert portfolio_resp.status_code == 200
    portfolio = portfolio_resp.json()
    assert portfolio.get("success") is True
    assert isinstance(portfolio.get("positions"), list)

    history_resp = client.get("/api/chat/history", params={"session_id": "public:anonymous:smoke", "limit": 5})
    assert history_resp.status_code == 200
    history = history_resp.json()
    assert history.get("success") is True
    assert isinstance(history.get("messages"), list)


def test_quote_demo_smoke_has_evidence_without_network(monkeypatch):
    """行情 smoke 固定走 Demo，验证证据字段，不触发外部行情网络。"""
    monkeypatch.setenv("FINSIGHT_DEMO_MODE", "true")

    with TestClient(app) as test_client:
        resp = test_client.get("/api/quote/AAPL")

    assert resp.status_code == 200
    payload = resp.json()
    data = payload["data"]
    assert payload["ticker"] == "AAPL"
    assert data["source"] == "demo"
    assert data["freshness_status"] == "demo"
    assert data["fallback_level"] == 2
    assert data["evidence"]["degraded"] is True
