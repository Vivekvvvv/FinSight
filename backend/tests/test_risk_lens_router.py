# -*- coding: utf-8 -*-
"""risk-lens 路由回归（R46）。

历史 bug：路由把 list_reports 的 list[dict] 返回值当 {"items": [...]} 用
（reports.extend(ticker_reports.get("items", []))），任何有持仓的用户请求
即抛 AttributeError，被宽 except 压成 200 空壳（success=False, 全空字段）
——端点对真实用户完全不可用，空持仓反而"正常"，掩盖了故障。
调度器同款循环（risk_snapshot_scheduler.py）当时已修，路由漏改。
"""
from __future__ import annotations

from fastapi.testclient import TestClient

_SESSION = "private:default_user:default"


def _client(monkeypatch) -> TestClient:
    from backend.api import main

    monkeypatch.setattr(
        main, "_rate_limiter",
        main.SimpleRateLimiter(limit_per_window=100, window_seconds=60, enabled=False),
    )
    return TestClient(main.app)


def test_risk_lens_returns_real_lens_for_user_with_positions(monkeypatch):
    """有持仓时必须返回真实风险透镜，而非异常压成的 success=False 空壳。"""
    import backend.services.portfolio_store as portfolio_store
    import backend.services.report_index as report_index

    monkeypatch.setattr(
        portfolio_store,
        "get_positions",
        lambda session_id: [
            {"ticker": "AAPL", "shares": 10, "avg_cost": 150.0, "currency": "USD"},
        ],
    )

    class _FakeStore:
        def list_reports(self, **kwargs):
            # 与真实实现同构：返回 list[dict]，不是 {"items": [...]}
            return [
                {
                    "report_id": "r1",
                    "ticker": "AAPL",
                    "generated_at": "2026-07-01T00:00:00+00:00",
                    "confidence_score": 0.8,
                }
            ]

    monkeypatch.setattr(report_index, "get_report_index_store", lambda: _FakeStore())

    with _client(monkeypatch) as client:
        resp = client.get(
            "/api/portfolio/risk-lens",
            params={"session_id": _SESSION},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body.get("success") is True, f"risk-lens 被压成空壳: {body.get('error')}"
    assert "error" not in body
