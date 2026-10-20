# -*- coding: utf-8 -*-
"""晨报：报价取数失败不能被渲染成"整体情绪：中性 / 波动平稳"。

`_fetch_ticker_data` 里价格取数异常只记 debug，snapshot 留空 → price 为 None、
change_pct 为 None；旧代码 `_classify_change(None)` 与 `_derive_market_mood`
（valid==0）都落到 "neutral"，于是晨报把"一只报价都没拿到"写成"整体情绪：中性"，
操作建议还给出"今日持仓波动平稳，建议维持当前仓位"——从缺失数据里编出的结论
（项目规则 2）。
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.api.morning_brief_router as morning_brief_module
from backend.api.morning_brief_router import (
    MorningBriefRouterDeps,
    create_morning_brief_router,
)
from backend.dashboard.cache import DashboardCache
from backend.security.auth import Principal, get_current_user


def _brief(price_fn, monkeypatch) -> dict:
    monkeypatch.setattr(morning_brief_module, "dashboard_cache", DashboardCache())
    app = FastAPI()
    app.include_router(
        create_morning_brief_router(
            MorningBriefRouterDeps(
                resolve_thread_id=lambda session_id: str(session_id),
                get_portfolio_positions=lambda _session_id: [],
                get_stock_price=price_fn,
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
            json={"session_id": "private:alice:default", "tickers": ["AAPL"]},
        )
    assert response.status_code == 200
    return response.json()["brief"]


def test_price_fetch_failure_does_not_read_as_neutral_mood(monkeypatch):
    def _raise(_ticker):
        raise RuntimeError("quote source down")

    brief = _brief(_raise, monkeypatch)

    assert brief["market_mood"] == "unknown"
    assert "整体情绪：中性" not in brief["summary"]
    assert "暂不判断整体情绪" in brief["summary"]
    assert brief["action_items"] == ["行情涨跌数据不足，暂不给出仓位建议"]
    assert "波动平稳" not in str(brief)
    assert brief["price_unavailable"] == ["AAPL"]
    assert brief["degraded"] is True


def test_missing_change_percent_also_yields_unknown_mood(monkeypatch):
    """有价无涨跌（partial quote）同样没测到方向，不能算中性。"""
    brief = _brief(lambda _ticker: {"price": 100.0}, monkeypatch)

    assert brief["market_mood"] == "unknown"
    assert "暂不判断整体情绪" in brief["summary"]
    assert brief["action_items"] == ["行情涨跌数据不足，暂不给出仓位建议"]
    # 报价本身拿到了，不算 price_unavailable
    assert "price_unavailable" not in brief


def test_genuine_flat_day_still_reads_as_neutral(monkeypatch):
    brief = _brief(
        lambda _ticker: {"price": 100.0, "change": 0.0, "change_percent": 0.0},
        monkeypatch,
    )

    assert brief["market_mood"] == "neutral"
    assert "整体情绪：中性" in brief["summary"]
    assert brief["action_items"] == ["今日持仓波动平稳，建议维持当前仓位"]
    assert "degraded" not in brief


def test_degraded_price_brief_is_not_cached(monkeypatch):
    """一次报价源抖动不该被 30min TTL 钉死成"数据不足"。"""
    monkeypatch.setattr(morning_brief_module, "dashboard_cache", DashboardCache())
    calls: list[str] = []

    def _raise(ticker):
        calls.append(ticker)
        raise RuntimeError("quote source down")

    app = FastAPI()
    app.include_router(
        create_morning_brief_router(
            MorningBriefRouterDeps(
                resolve_thread_id=lambda session_id: str(session_id),
                get_portfolio_positions=lambda _session_id: [],
                get_stock_price=_raise,
                get_company_news=lambda _ticker, _limit: [],
            )
        )
    )
    app.dependency_overrides[get_current_user] = lambda: Principal(
        user_id="alice", role="user", auth_type="api_key",
    )
    payload = {"session_id": "private:alice:default", "tickers": ["AAPL"]}
    with TestClient(app) as client:
        first = client.post("/api/morning-brief/generate", json=payload)
        second = client.post("/api/morning-brief/generate", json=payload)

    assert first.json()["brief"]["degraded"] is True
    assert second.json()["brief"]["degraded"] is True
    assert len(calls) == 2, "degraded brief must not be served from cache"
