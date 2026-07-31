from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.morning_brief_router import MorningBriefRouterDeps, create_morning_brief_router
from backend.security.auth import Principal, get_current_user


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
