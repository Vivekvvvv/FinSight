import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.rebalance_router import RebalanceRouterDeps, create_rebalance_router
from backend.services.rebalance_engine import RebalanceEngine


def _build_client(
    *,
    get_stock_price,
    get_company_info,
) -> TestClient:
    app = FastAPI()
    app.include_router(
        create_rebalance_router(
            RebalanceRouterDeps(
                rebalance_engine=RebalanceEngine(),
                get_stock_price=get_stock_price,
                get_company_info=get_company_info,
            )
        )
    )
    return TestClient(app)


def test_generate_rebalance_degrades_when_live_price_missing():
    client = _build_client(
        get_stock_price=lambda _ticker: {},
        get_company_info=lambda _ticker: "- Sector: Technology",
    )

    payload = {
        "session_id": "public:test_user:thread-1",
        "portfolio": [
            {"ticker": "AAPL", "shares": 10},
            {"ticker": "MSFT", "shares": 5},
        ],
    }
    response = client.post("/api/rebalance/suggestions/generate", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["degraded_mode"] is True
    assert data["actions"] == []
    assert "missing_live_prices" in (data.get("fallback_reason") or "")


def test_generate_rebalance_returns_actions_when_inputs_complete():
    price_map = {"AAPL": 200.0, "MSFT": 100.0}
    client = _build_client(
        get_stock_price=lambda ticker: {"price": price_map[ticker]},
        get_company_info=lambda _ticker: "- Sector: Technology",
    )

    payload = {
        "session_id": "public:test_user:thread-2",
        "portfolio": [
            {"ticker": "AAPL", "shares": 10},
            {"ticker": "MSFT", "shares": 5},
        ],
        "constraints": {
            "max_single_position_pct": 55,
            "max_turnover_pct": 30,
            "sector_concentration_limit": 100,
            "min_action_delta_pct": 1,
        },
    }
    response = client.post("/api/rebalance/suggestions/generate", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["degraded_mode"] is False
    assert data.get("fallback_reason") in (None, "")
    assert len(data["actions"]) >= 1


def test_rebalance_endpoints_reject_oversized_portfolio_before_fetching():
    calls = []

    def get_stock_price(ticker):
        calls.append(ticker)
        return {"price": 1.0}

    client = _build_client(
        get_stock_price=get_stock_price,
        get_company_info=lambda _ticker: "- Sector: Technology",
    )
    payload = {
        "session_id": "public:test_user:thread-limit",
        "portfolio": [{"ticker": f"T{index}", "shares": 1} for index in range(201)],
    }

    for path in (
        "/api/rebalance/suggestions/generate",
        "/api/rebalance/suggestions/generate-stream",
    ):
        response = client.post(path, json=payload)
        assert response.status_code == 422

    assert calls == []


@pytest.mark.parametrize(
    "portfolio",
    [
        [{"ticker": "A" * 33, "shares": 1}],
        [{"ticker": "AAPL", "shares": -1}],
        [{"ticker": "AAPL", "shares": 1}, {"ticker": " aapl ", "shares": 2}],
        [{"ticker": "AAPL", "shares": 1, "sector": "x" * 129}],
        [{"ticker": "AAPL", "shares": 1, "metadata": "x" * (256 * 1024)}],
    ],
)
def test_rebalance_endpoints_reject_invalid_positions_before_fetching(portfolio):
    calls: list[str] = []
    client = _build_client(
        get_stock_price=lambda ticker: calls.append(ticker) or {"price": 1.0},
        get_company_info=lambda ticker: calls.append(ticker) or "- Sector: Technology",
    )
    payload = {
        "session_id": "public:test_user:thread-validation",
        "portfolio": portfolio,
    }

    for path in (
        "/api/rebalance/suggestions/generate",
        "/api/rebalance/suggestions/generate-stream",
    ):
        response = client.post(path, json=payload)
        assert response.status_code == 422

    assert calls == []


@pytest.mark.parametrize("limit", [-1, 0, 51])
def test_rebalance_list_rejects_out_of_range_limit_before_store(monkeypatch, limit):
    from backend.api import rebalance_router as module

    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(
        module,
        "list_suggestions",
        lambda session_id, limit: calls.append((session_id, limit)) or [],
    )
    client = _build_client(
        get_stock_price=lambda _ticker: {},
        get_company_info=lambda _ticker: {},
    )

    response = client.get(
        "/api/rebalance/suggestions",
        params={"session_id": "public:test_user:thread-list", "limit": limit},
    )

    assert response.status_code == 422
    assert calls == []


def test_rebalance_patch_rejects_oversized_suggestion_id_before_store(monkeypatch):
    from backend.api import rebalance_router as module

    calls = []
    monkeypatch.setattr(
        module,
        "patch_suggestion",
        lambda *args, **kwargs: calls.append((args, kwargs)) or True,
    )
    client = _build_client(
        get_stock_price=lambda _ticker: {},
        get_company_info=lambda _ticker: {},
    )

    response = client.patch(
        f"/api/rebalance/suggestions/{'x' * 129}",
        json={"status": "viewed"},
    )

    assert response.status_code == 422
    assert calls == []
