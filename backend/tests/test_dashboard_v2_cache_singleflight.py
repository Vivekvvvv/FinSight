# -*- coding: utf-8 -*-
import asyncio

import pytest

import backend.api.dashboard_router as dashboard_router_module
import backend.dashboard.cache as cache_module
from backend.dashboard.cache import DashboardCache
from backend.dashboard.insights_engine import InsightsOrchestrator


def test_dashboard_failure_marker_roundtrip():
    marker = dashboard_router_module._make_failure_marker("peers_unavailable")
    assert dashboard_router_module._is_failure_marker(marker) is True
    assert dashboard_router_module._failure_reason_from_marker(marker) == "peers_unavailable"
    assert dashboard_router_module._failure_reason_from_marker({}) is None


@pytest.mark.asyncio
async def test_dashboard_singleflight_deduplicates_same_key():
    call_count = 0

    async def slow_fetch():
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.05)
        return {"ok": True}

    first, second = await asyncio.gather(
        dashboard_router_module._singleflight_call("MSFT:valuation", slow_fetch),
        dashboard_router_module._singleflight_call("MSFT:valuation", slow_fetch),
    )

    assert first == {"ok": True}
    assert second == {"ok": True}
    assert call_count == 1
    assert "MSFT:valuation" not in dashboard_router_module._singleflight_tasks


def test_insights_collect_data_ignores_failure_marker():
    cache = DashboardCache()
    cache.set(
        "AAPL",
        "technicals",
        {"__dashboard_failure__": True, "reason": "technicals_unavailable"},
        ttl=60,
    )
    cache.set(
        "AAPL",
        "news",
        {"market": [{"title": "Macro easing"}], "impact": []},
        ttl=60,
    )

    orchestrator = InsightsOrchestrator(cache=cache)
    data = orchestrator._collect_dashboard_data("AAPL")

    assert data["technicals"] == {}
    assert len(data["news"].get("market", [])) == 1


@pytest.mark.parametrize("invalid_ttl", [float("nan"), float("inf"), -1])
def test_dashboard_cache_invalid_ttl_expires_immediately(monkeypatch, invalid_ttl):
    monkeypatch.setattr(cache_module.time, "time", lambda: 100.0)
    cache = DashboardCache()

    cache.set("AAPL", "snapshot", {"price": 1}, ttl=invalid_ttl)

    monkeypatch.setattr(cache_module.time, "time", lambda: 100.1)
    assert cache.get("AAPL", "snapshot") is None


@pytest.mark.parametrize("invalid_ttl", [float("nan"), float("inf"), -1])
def test_dashboard_cache_invalid_stale_ttl_uses_bounded_default(monkeypatch, invalid_ttl):
    monkeypatch.setattr(cache_module.time, "time", lambda: 100.0)
    cache = DashboardCache()
    cache.set("AAPL", "insights", {"ok": True}, ttl=1)

    monkeypatch.setattr(cache_module.time, "time", lambda: 100.0 + 1 + cache.TTL_INSIGHTS_STALE + 0.1)
    assert cache.get_with_stale("AAPL", "insights", stale_ttl=invalid_ttl) == (None, False)
