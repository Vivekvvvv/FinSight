# -*- coding: utf-8 -*-
"""Portfolio API validation tests for cost-basis and bulk import payloads."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_update_position_rejects_negative_avg_cost(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")
    from backend.api import main

    monkeypatch.setattr(main, "_rate_limiter", main.SimpleRateLimiter(limit_per_window=100, window_seconds=60, enabled=False))

    with TestClient(main.app) as client:
        resp = client.put(
            "/api/portfolio/positions/AAPL",
            params={"session_id": "private:default_user:default"},
            json={"shares": 10, "avg_cost": -1},
        )

    assert resp.status_code == 422


def test_bulk_sync_rejects_negative_cost_and_shares(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")
    from backend.api import main

    monkeypatch.setattr(main, "_rate_limiter", main.SimpleRateLimiter(limit_per_window=100, window_seconds=60, enabled=False))

    with TestClient(main.app) as client:
        cost_resp = client.post(
            "/api/portfolio/positions",
            json={
                "session_id": "private:default_user:default",
                "positions": [{"ticker": "AAPL", "shares": 1, "avg_cost": -10}],
            },
        )
        shares_resp = client.post(
            "/api/portfolio/positions",
            json={
                "session_id": "private:default_user:default",
                "positions": [{"ticker": "MSFT", "shares": -1, "avg_cost": 300}],
            },
        )

    assert cost_resp.status_code == 422
    assert shares_resp.status_code == 422


def test_bulk_write_endpoints_reject_oversized_position_lists(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")
    from backend.api import main

    monkeypatch.setattr(main, "_rate_limiter", main.SimpleRateLimiter(limit_per_window=100, window_seconds=60, enabled=False))
    payload = {
        "session_id": "private:default_user:default",
        "positions": [{"ticker": f"T{index}", "shares": 1} for index in range(201)],
    }

    with TestClient(main.app) as client:
        sync_resp = client.post("/api/portfolio/positions", json=payload)
        import_resp = client.post("/api/portfolio/bulk", json=payload)

    assert sync_resp.status_code == 422
    assert import_resp.status_code == 422


def test_portfolio_writes_reject_invalid_tickers_and_long_tags(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")
    from backend.api import main
    from backend.api import portfolio_router as module

    calls: list[str] = []
    monkeypatch.setattr(
        main,
        "_rate_limiter",
        main.SimpleRateLimiter(limit_per_window=100, window_seconds=60, enabled=False),
    )
    monkeypatch.setattr(module, "update_position", lambda **_kwargs: calls.append("update"))
    monkeypatch.setattr(module, "remove_position", lambda **_kwargs: calls.append("remove"))
    monkeypatch.setattr(module, "sync_positions", lambda *_args, **_kwargs: calls.append("sync"))

    session_id = "private:default_user:default"
    with TestClient(main.app) as client:
        bulk_resp = client.post(
            "/api/portfolio/bulk",
            json={
                "session_id": session_id,
                "positions": [{"ticker": "NOT A TICKER", "shares": 1}],
            },
        )
        sync_resp = client.post(
            "/api/portfolio/positions",
            json={
                "session_id": session_id,
                "positions": [{"ticker": "AAPL", "shares": 1, "tags": ["x" * 65]}],
            },
        )
        update_resp = client.put(
            "/api/portfolio/positions/NOT%20A%20TICKER",
            params={"session_id": session_id},
            json={"shares": 1},
        )
        delete_resp = client.delete(
            "/api/portfolio/positions/NOT%20A%20TICKER",
            params={"session_id": session_id},
        )

    assert bulk_resp.status_code == 422
    assert sync_resp.status_code == 422
    assert update_resp.status_code == 422
    assert delete_resp.status_code == 422
    assert calls == []


def test_portfolio_writes_reject_non_finite_numbers(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")
    from backend.api import main
    from backend.api import portfolio_router as module

    calls: list[str] = []
    monkeypatch.setattr(
        main,
        "_rate_limiter",
        main.SimpleRateLimiter(limit_per_window=100, window_seconds=60, enabled=False),
    )
    monkeypatch.setattr(module, "update_position", lambda **_kwargs: calls.append("update"))
    monkeypatch.setattr(module, "sync_positions", lambda *_args, **_kwargs: calls.append("sync"))
    session_id = "private:default_user:default"

    with TestClient(main.app) as client:
        sync_resp = client.post(
            "/api/portfolio/positions",
            json={
                "session_id": session_id,
                "positions": [{"ticker": "AAPL", "shares": "inf"}],
            },
        )
        update_resp = client.put(
            "/api/portfolio/positions/AAPL",
            params={"session_id": session_id},
            json={"shares": 1, "avg_cost": "nan"},
        )

    assert sync_resp.status_code == 422
    assert update_resp.status_code == 422
    assert calls == []


def test_portfolio_summary_does_not_fetch_quote_for_invalid_stored_ticker(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")
    from backend.api import main
    from backend.api import portfolio_router as module

    quote_calls = []
    monkeypatch.setattr(
        main,
        "_rate_limiter",
        main.SimpleRateLimiter(limit_per_window=100, window_seconds=60, enabled=False),
    )
    monkeypatch.setattr(
        module,
        "get_positions",
        lambda _session_id: [{"ticker": "A" * 21, "shares": 1, "avg_cost": 10}],
    )

    async def _quote(ticker):
        quote_calls.append(ticker)
        return {}, None

    monkeypatch.setattr(module, "_resolve_quote_for_portfolio", _quote)
    with TestClient(main.app) as client:
        response = client.get(
            "/api/portfolio/summary",
            params={"session_id": "private:default_user:default"},
        )

    assert response.status_code == 200
    assert response.json()["positions"][0]["price_source"] == "avg_cost_fallback"
    assert quote_calls == []


def test_portfolio_summary_handles_invalid_stored_numbers(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")
    from backend.api import main
    from backend.api import portfolio_router as module

    monkeypatch.setattr(
        main,
        "_rate_limiter",
        main.SimpleRateLimiter(limit_per_window=100, window_seconds=60, enabled=False),
    )
    monkeypatch.setattr(
        module,
        "get_positions",
        lambda _session_id: [
            {"ticker": "AAPL", "shares": "bad", "avg_cost": -10},
            {"ticker": "MSFT", "shares": "inf", "avg_cost": "nan"},
        ],
    )

    async def _no_quote(_position):
        return None, None

    monkeypatch.setattr(module, "_resolve_quote_for_stored_position", _no_quote)
    with TestClient(main.app) as client:
        response = client.get(
            "/api/portfolio/summary",
            params={"session_id": "private:default_user:default"},
        )

    payload = response.json()
    assert response.status_code == 200
    assert payload["total_value"] == 0.0
    assert payload["total_cost"] == 0.0
    assert all(item["market_value"] == 0.0 for item in payload["positions"])


def test_portfolio_summary_rejects_non_positive_live_price(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")
    from backend.api import main
    from backend.api import portfolio_router as module

    monkeypatch.setattr(
        main,
        "_rate_limiter",
        main.SimpleRateLimiter(limit_per_window=100, window_seconds=60, enabled=False),
    )
    monkeypatch.setattr(
        module,
        "get_positions",
        lambda _session_id: [{"ticker": "AAPL", "shares": 2, "avg_cost": 10}],
    )

    async def _bad_quote(_position):
        return {"price": -5, "source": "bad-provider"}, None

    monkeypatch.setattr(module, "_resolve_quote_for_stored_position", _bad_quote)
    with TestClient(main.app) as client:
        response = client.get(
            "/api/portfolio/summary",
            params={"session_id": "private:default_user:default"},
        )

    payload = response.json()
    assert response.status_code == 200
    assert payload["priced_count"] == 0
    assert payload["total_value"] == 20.0
    assert payload["positions"][0]["price_source"] == "avg_cost_fallback"
