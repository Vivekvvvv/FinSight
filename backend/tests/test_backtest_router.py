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
