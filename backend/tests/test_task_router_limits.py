from datetime import datetime, timedelta

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


def test_daily_tasks_naive_generated_at_uses_real_age_not_999():
    """report_generator.py、report/ir.py、report/validator.py 用
    datetime.now().isoformat() 写 naive generated_at。裸 fromisoformat 得
    naive datetime，与 aware now 相减抛 TypeError 被 except 吞掉 → age_days
    恒 999 → 刚生成的报告也发"更新报告"任务（reason 显示"距今 999 天"），
    同时 _check_recent_report 早退把"查看最新报告"任务压掉。"""
    class _NaiveReportStore:
        def list_reports(self, **_kwargs):
            return [{
                "ticker": "NAIVECO",
                "report_id": "rpt-naive-1",
                # 与 report_generator.py:46 同款的 naive 时间戳：5 分钟前
                "generated_at": (datetime.now() - timedelta(minutes=5)).isoformat(),
                "confidence_score": 0.8,
            }]

    principal = Principal(user_id="task-user", role="user", auth_type="api_key")
    deps = TaskRouterDeps(
        resolve_thread_id=lambda session_id: session_id,
        get_report_index_store=lambda: _NaiveReportStore(),
        get_portfolio_positions=lambda _session_id: [
            {"ticker": "NAIVECO", "shares": 1, "avg_cost": 1}
        ],
        get_stock_price=lambda _ticker: None,
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
    tasks = response.json()["tasks"]
    # 5 分钟前的报告不应被当作过期（999 天）触发重新分析
    assert all("999" not in task["reason"] for task in tasks)
    assert all(task["category"] != "reanalyze" for task in tasks)
    # 应改为生成"查看最新报告"任务
    assert any(task["category"] == "review" for task in tasks)
