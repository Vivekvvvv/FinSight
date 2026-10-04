from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.api.morning_brief_router as morning_brief_module
from backend.api.morning_brief_router import MorningBriefRouterDeps, create_morning_brief_router
from backend.dashboard.cache import DashboardCache
from backend.security.auth import Principal, get_current_user


def _make_brief_app(positions_fn, price_fn=None, news_fn=None):
    app = FastAPI()
    app.include_router(
        create_morning_brief_router(
            MorningBriefRouterDeps(
                resolve_thread_id=lambda session_id: str(session_id),
                get_portfolio_positions=positions_fn,
                get_stock_price=price_fn or (lambda _ticker: {}),
                get_company_news=news_fn or (lambda _ticker, _limit: []),
            )
        )
    )
    app.dependency_overrides[get_current_user] = lambda: Principal(
        user_id="alice", role="user", auth_type="api_key",
    )
    return app


def test_morning_brief_positions_fetch_failure_not_reported_as_empty():
    """持仓存储读取失败被静默降级成空持仓：用户看到"请先添加持仓"，
    照做会走 sync_positions 全量替换覆盖真实持仓——失败态必须与空态区分。"""
    def _raising_positions(_session_id):
        raise RuntimeError("store down")

    app = _make_brief_app(_raising_positions)
    with TestClient(app) as client:
        response = client.post(
            "/api/morning-brief/generate",
            json={"session_id": "private:alice:default", "tickers": []},
        )

    assert response.status_code == 200
    brief = response.json()["brief"]
    assert brief.get("positions_unavailable") is True
    assert "无持仓" not in brief["summary"]


def test_morning_brief_positions_failure_flags_brief_and_skips_cache(monkeypatch):
    """持仓读取失败但请求自带 tickers：brief 须标 positions_unavailable，
    且不得按 30min TTL 缓存——一次存储抖动不该把"持仓缺失"假象钉死半小时
    （恢复后同 key 请求仍命中降级缓存）。"""
    monkeypatch.setattr(morning_brief_module, "dashboard_cache", DashboardCache())
    price_calls: list[str] = []

    def _raising_positions(_session_id):
        raise RuntimeError("store down")

    app = _make_brief_app(
        _raising_positions,
        price_fn=lambda ticker: price_calls.append(ticker) or {"price": 1},
    )
    payload = {"session_id": "private:alice:default", "tickers": ["AAPL"]}
    with TestClient(app) as client:
        r1 = client.post("/api/morning-brief/generate", json=payload)
        r2 = client.post("/api/morning-brief/generate", json=payload)

    for resp in (r1, r2):
        assert resp.status_code == 200
        assert resp.json()["brief"].get("positions_unavailable") is True
    # 两次请求都真实取价 → 降级 brief 未进缓存
    assert len(price_calls) == 2


def test_morning_brief_rejects_oversized_ticker_before_dependencies():
    calls: list[str] = []
    app = FastAPI()
    app.include_router(
        create_morning_brief_router(
            MorningBriefRouterDeps(
                resolve_thread_id=lambda session_id: str(session_id),
                get_portfolio_positions=lambda _session_id: calls.append("positions") or [],
                get_stock_price=lambda _ticker: calls.append("price") or {},
                get_company_news=lambda _ticker, _limit: calls.append("news") or [],
            )
        )
    )
    app.dependency_overrides[get_current_user] = lambda: Principal(
        user_id="alice", role="user", auth_type="api_key",
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/morning-brief/generate",
            json={
                "session_id": "private:alice:default",
                "tickers": ["A" * 33],
            },
        )

    assert response.status_code == 422
    assert calls == []
