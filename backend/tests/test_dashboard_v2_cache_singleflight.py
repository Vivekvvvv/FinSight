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


def test_as_iso_rejects_boolean_timestamp():
    assert dashboard_router_module._as_iso(True) == ""
    assert dashboard_router_module._as_iso(False) == ""


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


@pytest.mark.asyncio
async def test_singleflight_cancelled_waiter_does_not_kill_shared_fetch():
    """单个 waiter 取消不得连带杀死共享 fetch。

    await 裸 Task 会把取消传播进任务本身：任一调用方断连/被 gather 取消 →
    共享 fetch 被杀 → 其他 waiter 的 await task 也抛 CancelledError →
    上层 return_exceptions 记 {key}_error 并写 30s failure marker——
    无辜请求被一次无关取消污染。shield 隔离各 waiter 的取消。"""
    call_count = 0
    started = asyncio.Event()

    async def slow_fetch():
        nonlocal call_count
        call_count += 1
        started.set()
        await asyncio.sleep(0.05)
        return {"ok": True}

    waiter_a = asyncio.create_task(
        dashboard_router_module._singleflight_call("MSFT:valuation", slow_fetch)
    )
    await started.wait()
    waiter_b = asyncio.create_task(
        dashboard_router_module._singleflight_call("MSFT:valuation", slow_fetch)
    )
    await asyncio.sleep(0.01)  # 让 waiter_b 完成 attach 后再取消 a
    waiter_a.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter_a

    assert await waiter_b == {"ok": True}
    assert call_count == 1


@pytest.mark.asyncio
async def test_dashboard_news_failure_writes_marker_not_full_ttl_shell(monkeypatch):
    """fetch_news 返回 None（两源都抛，R51）时，router 把空壳
    {"market":[],"impact":[]} 按 TTL_NEWS=300s 缓存——后续请求把它当
    高置信度 cache hit（不标 fallback、confidence 0.85），正是 R51/R57
    要修的病，只是上移了一层。应与同函数 v2/g2 一致写 failure marker：
    命中时回报 fallback_reason 且短 TTL 重试。"""
    cache = DashboardCache()
    monkeypatch.setattr(dashboard_router_module, "dashboard_cache", cache)
    monkeypatch.setattr(
        dashboard_router_module, "fetch_snapshot", lambda *a, **k: {"price": 1}
    )
    monkeypatch.setattr(
        dashboard_router_module, "fetch_market_chart", lambda *a, **k: [{"t": 1}]
    )
    monkeypatch.setattr(
        dashboard_router_module, "fetch_news", lambda *a, **k: None
    )
    monkeypatch.setattr(
        dashboard_router_module, "fetch_macro_snapshot", lambda *a, **k: None
    )

    resp = await dashboard_router_module.get_dashboard(symbol="BTC-USD")

    assert resp.data.meta["news_market"]["fallback_reason"] == "news_unavailable"
    cached = cache.get("BTC-USD", "news")
    assert dashboard_router_module._is_failure_marker(cached), (
        f"news 故障应按 failure marker 短缓存，实际缓存: {cached!r}"
    )

    # 第二次请求命中 failure marker：必须仍标 fallback（而非高置信度空壳）。
    resp2 = await dashboard_router_module.get_dashboard(symbol="BTC-USD")
    meta = resp2.data.meta["news_market"]
    assert meta["source_type"] == "failure_cache"
    assert meta["fallback_reason"] == "news_unavailable"
    assert meta["fallback_used"] is True


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


@pytest.mark.parametrize("invalid_ttl", [float("nan"), float("inf"), -1, True, False])
def test_dashboard_cache_invalid_ttl_expires_immediately(monkeypatch, invalid_ttl):
    monkeypatch.setattr(cache_module.time, "time", lambda: 100.0)
    cache = DashboardCache()

    cache.set("AAPL", "snapshot", {"price": 1}, ttl=invalid_ttl)

    monkeypatch.setattr(cache_module.time, "time", lambda: 100.1)
    assert cache.get("AAPL", "snapshot") is None


@pytest.mark.parametrize("invalid_ttl", [float("nan"), float("inf"), -1, True, False])
def test_dashboard_cache_invalid_stale_ttl_uses_bounded_default(monkeypatch, invalid_ttl):
    monkeypatch.setattr(cache_module.time, "time", lambda: 100.0)
    cache = DashboardCache()
    cache.set("AAPL", "insights", {"ok": True}, ttl=1)

    monkeypatch.setattr(cache_module.time, "time", lambda: 100.0 + 1 + cache.TTL_INSIGHTS_STALE + 0.1)
    assert cache.get_with_stale("AAPL", "insights", stale_ttl=invalid_ttl) == (None, False)
