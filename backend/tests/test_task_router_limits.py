from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.task_router import TaskRouterDeps, create_task_router
from backend.security.auth import Principal, get_current_user


class _ReportStore:
    def list_reports(self, **_kwargs):
        return []


def test_daily_tasks_rejects_oversized_watchlist_before_price_fetch():
    price_calls = []
    principal = Principal(user_id="task-user", role="user", auth_type="api_key")
    deps = TaskRouterDeps(
        resolve_thread_id=lambda session_id: session_id,
        get_report_index_store=lambda: _ReportStore(),
        get_portfolio_positions=lambda _session_id: [],
        get_stock_price=lambda ticker: price_calls.append(ticker),
    )
    app = FastAPI()
    app.include_router(create_task_router(deps))
    app.dependency_overrides[get_current_user] = lambda: principal
    watchlist = ",".join(f"T{index}" for index in range(51))

    with TestClient(app) as client:
        response = client.get(
            "/api/tasks/daily",
            params={"session_id": principal.session_id, "watchlist": watchlist},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Too many watchlist tickers"
    assert price_calls == []


def test_daily_tasks_rejects_oversized_ticker_before_price_fetch():
    price_calls = []
    principal = Principal(user_id="task-user", role="user", auth_type="api_key")
    deps = TaskRouterDeps(
        resolve_thread_id=lambda session_id: session_id,
        get_report_index_store=lambda: _ReportStore(),
        get_portfolio_positions=lambda _session_id: [],
        get_stock_price=lambda ticker: price_calls.append(ticker),
    )
    app = FastAPI()
    app.include_router(create_task_router(deps))
    app.dependency_overrides[get_current_user] = lambda: principal

    with TestClient(app) as client:
        response = client.get(
            "/api/tasks/daily",
            params={"session_id": principal.session_id, "watchlist": "A" * 33},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid watchlist ticker"
    assert price_calls == []


def test_daily_tasks_ignores_oversized_persisted_tickers_before_price_fetch():
    class _DirtyReportStore:
        def list_reports(self, **_kwargs):
            return [{"ticker": "R" * 33}]

    price_calls = []
    principal = Principal(user_id="task-user", role="user", auth_type="api_key")
    deps = TaskRouterDeps(
        resolve_thread_id=lambda session_id: session_id,
        get_report_index_store=lambda: _DirtyReportStore(),
        get_portfolio_positions=lambda _session_id: [{"ticker": "P" * 33, "shares": 1}],
        get_stock_price=lambda ticker: price_calls.append(ticker),
    )
    app = FastAPI()
    app.include_router(create_task_router(deps))
    app.dependency_overrides[get_current_user] = lambda: principal

    with TestClient(app) as client:
        response = client.get(
            "/api/tasks/daily",
            params={"session_id": principal.session_id},
        )

    assert response.status_code == 200
    assert response.json()["watchlist"] == []
    assert price_calls == []
