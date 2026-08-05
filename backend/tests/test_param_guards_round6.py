# -*- coding: utf-8 -*-
"""E 类参数防护 + A5/A10 rebalance 属主回归（docs/BUG_AUDIT_2026-07-04.md）。

E1/E2/E4 是无条件参数校验，dev 模式（conftest 默认 DEV_MODE=1）直接测；
E3 admin 门与 A5/A10 越权拒绝需要非 admin 的生产主体，
照 backend/tests/test_authz_round6.py 的范式切到 prod 主体（release-key-1 → alice, role=user）。
"""
from __future__ import annotations

import math

from fastapi.testclient import TestClient


def _set_prod_env(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "0")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_BASE", "https://llm.test/v1")
    monkeypatch.setenv("OPENAI_COMPATIBLE_MODEL", "test-model")
    monkeypatch.setenv("POSTGRES_DB", "test")
    monkeypatch.setenv("POSTGRES_USER", "test")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test")
    monkeypatch.setenv("JWT_SECRET", "0123456789abcdef0123456789abcdef")
    monkeypatch.setenv("API_AUTH_KEYS", "release-key-1")
    monkeypatch.setenv(
        "API_AUTH_PRINCIPALS",
        '{"release-key-1":{"user_id":"alice","email":"alice@example.invalid","role":"user"}}',
    )


def _client(monkeypatch, *, prod: bool) -> TestClient:
    from backend.api import main

    if prod:
        _set_prod_env(monkeypatch)
    monkeypatch.setattr(
        main, "_rate_limiter",
        main.SimpleRateLimiter(limit_per_window=100, window_seconds=60, enabled=False),
    )
    return TestClient(main.app)


_KEY = {"x-api-key": "release-key-1"}


# ── E1: 组合优化蒙特卡洛次数上限 ────────────────────────────────


def test_e1_optimize_rejects_oversized_n_simulations(monkeypatch):
    with _client(monkeypatch, prod=False) as client:
        resp = client.post(
            "/api/portfolio/optimize",
            json={"tickers": ["AAPL", "MSFT"], "n_simulations": 100_000_000},
        )
    assert resp.status_code == 422


def test_e1_optimize_rejects_nonpositive_n_simulations(monkeypatch):
    with _client(monkeypatch, prod=False) as client:
        resp = client.post(
            "/api/portfolio/optimize",
            json={"tickers": ["AAPL", "MSFT"], "n_simulations": 0},
        )
    assert resp.status_code == 422


def test_e1_optimize_rejects_oversized_or_duplicate_tickers(monkeypatch):
    from backend import tools

    calls: list[str] = []
    monkeypatch.setattr(
        tools,
        "get_stock_historical_data",
        lambda ticker, **_kwargs: calls.append(ticker),
    )
    with _client(monkeypatch, prod=False) as client:
        oversized = client.post(
            "/api/portfolio/optimize",
            json={"tickers": ["A" * 33, "MSFT"]},
        )
        duplicate = client.post(
            "/api/portfolio/optimize",
            json={"tickers": ["AAPL", " aapl "]},
        )

    assert oversized.status_code == 422
    assert duplicate.status_code == 422
    assert calls == []


def test_e1_optimize_rejects_non_finite_risk_free_rate(monkeypatch):
    with _client(monkeypatch, prod=False) as client:
        response = client.post(
            "/api/portfolio/optimize",
            json={"tickers": ["AAPL", "MSFT"], "risk_free_rate": "inf"},
        )

    assert response.status_code == 422


def test_e1_optimize_filters_non_finite_historical_closes(monkeypatch):
    from backend import tools
    from backend.services import portfolio_optimizer

    captured: dict = {}
    rows = [
        {"close": value}
        for value in ([100 + index for index in range(20)] + ["nan", "inf", 0])
    ]
    monkeypatch.setattr(
        tools,
        "get_stock_historical_data",
        lambda _ticker, **_kwargs: {"kline_data": rows},
    )

    def _optimize_portfolio(**kwargs):
        captured.update(kwargs)
        return {"success": True}

    monkeypatch.setattr(portfolio_optimizer, "optimize_portfolio", _optimize_portfolio)
    with _client(monkeypatch, prod=False) as client:
        response = client.post(
            "/api/portfolio/optimize",
            json={"tickers": ["AAPL", "MSFT"], "n_simulations": 100},
        )

    assert response.status_code == 200
    assert len(captured["returns_matrix"]) == 2
    assert all(
        math.isfinite(value)
        for series in captured["returns_matrix"]
        for value in series
    )


# ── E2: 风险历史 days 夹紧到 [1, 90] ───────────────────────────


def test_e2_risk_history_clamps_negative_days(monkeypatch):
    from backend.api import risk_lens_router as module

    captured: dict = {}

    def _fake_history(*, session_id: str, user_id: str, days: int):
        captured["days"] = days
        return []

    monkeypatch.setattr(module, "get_risk_snapshots_history", _fake_history)
    with _client(monkeypatch, prod=False) as client:
        resp = client.get(
            "/api/portfolio/risk-lens/history",
            params={"session_id": "private:default_user:default", "days": -5},
        )
    assert resp.status_code == 200
    assert captured["days"] == 1  # 负值被夹紧，不透传存储层


# ── E3: POST /api/config 仅 admin 可写 ─────────────────────────


def test_e3_config_post_rejects_non_admin(monkeypatch):
    with _client(monkeypatch, prod=True) as client:
        resp = client.post("/api/config", json={"layout_mode": "wide"}, headers=_KEY)
    assert resp.status_code == 403


# ── E4: 研究笔记分页参数约束 ───────────────────────────────────


def test_e4_notes_rejects_negative_offset(monkeypatch):
    with _client(monkeypatch, prod=False) as client:
        resp = client.get(
            "/api/research-notes",
            params={"session_id": "private:default_user:default", "offset": -1},
        )
    assert resp.status_code == 422


def test_e4_notes_rejects_oversized_limit(monkeypatch):
    with _client(monkeypatch, prod=False) as client:
        resp = client.get(
            "/api/research-notes",
            params={"session_id": "private:default_user:default", "limit": 100000},
        )
    assert resp.status_code == 422


# ── A5/A10: rebalance 属主绑定 ─────────────────────────────────


def test_a10_rebalance_generate_rejects_forged_session(monkeypatch):
    with _client(monkeypatch, prod=True) as client:
        resp = client.post(
            "/api/rebalance/suggestions/generate",
            json={"session_id": "private:bob:default", "portfolio": [{"ticker": "AAPL", "shares": 1}]},
            headers=_KEY,
        )
    assert resp.status_code == 403


def test_a10_rebalance_list_rejects_forged_session(monkeypatch):
    with _client(monkeypatch, prod=True) as client:
        resp = client.get(
            "/api/rebalance/suggestions",
            params={"session_id": "private:bob:default"},
            headers=_KEY,
        )
    assert resp.status_code == 403


def test_a5_rebalance_patch_rejects_forged_session(monkeypatch):
    with _client(monkeypatch, prod=True) as client:
        resp = client.patch(
            "/api/rebalance/suggestions/sug-1",
            json={"status": "viewed", "session_id": "private:bob:default"},
            headers=_KEY,
        )
    assert resp.status_code == 403


def test_a5_rebalance_patch_scoped_to_owner_session(monkeypatch, tmp_path):
    """不声明 session_id 时，生产模式按认证主体过滤：猜到他人 suggestion_id 也改不动。"""
    from backend.services import portfolio_store as store

    monkeypatch.setattr(store, "_DB_PATH", tmp_path / "portfolio.db")
    store.save_suggestion("sug-bob-1", session_id="private:bob:default", data={"note": "x"})

    with _client(monkeypatch, prod=True) as client:
        resp = client.patch(
            "/api/rebalance/suggestions/sug-bob-1",
            json={"status": "viewed"},
            headers=_KEY,
        )
    assert resp.status_code == 404  # alice 的 session 过滤后无匹配行

    rows = store.list_suggestions("private:bob:default")
    assert rows and rows[0]["status"] == "draft"  # bob 的建议未被篡改
