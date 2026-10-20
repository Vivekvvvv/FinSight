# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import backtest_router as backtest_router_module


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(backtest_router_module.backtest_router)
    return TestClient(app)


def test_backtest_router_list_strategies(monkeypatch):
    class _FakeEngine:
        @staticmethod
        def list_strategies():
            return [{"id": "ma_cross"}]

    monkeypatch.setattr(backtest_router_module, "BacktestEngine", _FakeEngine)
    client = _build_client()

    response = client.get("/api/backtest/strategies")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["strategies"][0]["id"] == "ma_cross"


def test_backtest_router_run(monkeypatch):
    class _FakeEngine:
        @staticmethod
        def list_strategies():
            return []

        def run(self, **kwargs):
            return {
                "success": True,
                "ticker": kwargs["ticker"],
                "strategy": kwargs["strategy"],
                "metrics": {"total_return_pct": 12.3},
            }

    monkeypatch.setattr(backtest_router_module, "BacktestEngine", _FakeEngine)
    client = _build_client()

    response = client.post(
        "/api/backtest/run",
        json={
            "ticker": "AAPL",
            "strategy": "ma_cross",
            "params": {},
            "initial_cash": 100000,
            "t_plus_one": True,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["ticker"] == "AAPL"
    assert payload["metrics"]["total_return_pct"] == 12.3


def _engine_returning(result: dict):
    class _FakeEngine:
        def __init__(self):
            pass

        def run(self, **kwargs):
            return dict(result)

    return _FakeEngine


def test_backtest_market_data_outage_is_not_a_422_insufficient_history(monkeypatch):
    """行情源全挂时 engine 返回 insufficient_price_data + source=unavailable：
    那是上游故障（502），不能和"这只票历史确实不够长"（422）同形。"""
    monkeypatch.setattr(
        backtest_router_module,
        "BacktestEngine",
        _engine_returning({
            "success": False,
            "error": "insufficient_price_data",
            "ticker": "AAPL",
            "source": "unavailable",
            "points": 0,
        }),
    )

    response = _build_client().post(
        "/api/backtest/run", json={"ticker": "AAPL", "strategy": "ma_cross"}
    )

    assert response.status_code == 502
    assert "Market data unavailable" in response.json()["detail"]


def test_backtest_genuinely_short_history_stays_422(monkeypatch):
    monkeypatch.setattr(
        backtest_router_module,
        "BacktestEngine",
        _engine_returning({
            "success": False,
            "error": "insufficient_price_data",
            "ticker": "AAPL",
            "source": "historical",
            "points": 12,
        }),
    )

    response = _build_client().post(
        "/api/backtest/run", json={"ticker": "AAPL", "strategy": "ma_cross"}
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "insufficient_price_data"


def test_backtest_engine_failure_is_not_reported_as_success(monkeypatch):
    monkeypatch.setattr(
        backtest_router_module,
        "BacktestEngine",
        _engine_returning({"success": False, "error": "invalid_strategy_signals"}),
    )

    response = _build_client().post(
        "/api/backtest/run", json={"ticker": "AAPL", "strategy": "ma_cross"}
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "invalid_strategy_signals"


@pytest.mark.parametrize(
    "payload",
    [
        {"ticker": "A" * 33, "strategy": "ma_cross"},
        {"ticker": "AAPL", "strategy": "ma_cross", "params": {"period": {"nested": 1}}},
        {"ticker": "AAPL", "strategy": "ma_cross", "params": {"period": "not-a-number"}},
        {"ticker": "AAPL", "strategy": "ma_cross", "initial_cash": "inf"},
        {"ticker": "AAPL", "strategy": "ma_cross", "start_date": "2024-99-99"},
        {
            "ticker": "AAPL",
            "strategy": "ma_cross",
            "start_date": "2025-01-02",
            "end_date": "2025-01-01",
        },
        {
            "ticker": "AAPL",
            "strategy": "ma_cross",
            "params": {f"param-{index}": index for index in range(11)},
        },
    ],
)
def test_backtest_router_rejects_invalid_payload_before_engine(monkeypatch, payload):
    calls: list[str] = []

    class _FakeEngine:
        def __init__(self):
            calls.append("init")

    monkeypatch.setattr(backtest_router_module, "BacktestEngine", _FakeEngine)
    client = _build_client()

    response = client.post("/api/backtest/run", json=payload)

    assert response.status_code == 422
    assert calls == []
