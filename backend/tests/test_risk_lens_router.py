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


def _pin_quote(monkeypatch, price: float | None) -> None:
    """把路由的行情解析钉死，测试不触网。"""
    import backend.api.portfolio_router as portfolio_router

    async def _fake_quote(_ticker):
        return ({"price": price} if price is not None else None), None

    monkeypatch.setattr(portfolio_router, "_resolve_quote_for_portfolio", _fake_quote)


def _pin_positions(monkeypatch) -> None:
    import backend.services.portfolio_store as portfolio_store

    monkeypatch.setattr(
        portfolio_store,
        "get_positions",
        lambda session_id: [
            {"ticker": "AAPL", "shares": 10, "avg_cost": 150.0, "currency": "USD"},
        ],
    )


def test_risk_lens_returns_real_lens_for_user_with_positions(monkeypatch):
    """有持仓时必须返回真实风险透镜，而非异常压成的 success=False 空壳。"""
    import backend.services.report_index as report_index

    _pin_positions(monkeypatch)
    _pin_quote(monkeypatch, 150.0)

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
    # 有实时报价时按市价估值，且不算降级。
    assert body["total_value"] == 1500.0
    assert body["priced_count"] == 1
    assert body["degraded"] is False


def test_risk_lens_uses_live_quote_so_loss_positions_are_detected(monkeypatch):
    """持仓存储只有成本价：必须补上当前市价，否则亏损持仓恒为空。"""
    import backend.services.report_index as report_index

    _pin_positions(monkeypatch)
    _pin_quote(monkeypatch, 100.0)
    monkeypatch.setattr(
        report_index,
        "get_report_index_store",
        lambda: type("_S", (), {"list_reports": lambda self, **kw: []})(),
    )

    with _client(monkeypatch) as client:
        resp = client.get("/api/portfolio/risk-lens", params={"session_id": _SESSION})

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_value"] == 1000.0
    assert body["total_cost"] == 1500.0
    assert [item["related_symbol"] for item in body["loss_positions"]] == ["AAPL"]
    # -33%：超过 -10% 高风险阈值。
    assert body["loss_positions"][0]["severity"] == "high"
    assert body["degraded"] is False


def test_risk_lens_marks_cost_basis_fallback_as_degraded(monkeypatch):
    """行情全失败时退回成本价，但必须显式标记，不能当成当前市值。"""
    import backend.services.report_index as report_index

    _pin_positions(monkeypatch)
    _pin_quote(monkeypatch, None)
    monkeypatch.setattr(
        report_index,
        "get_report_index_store",
        lambda: type("_S", (), {"list_reports": lambda self, **kw: []})(),
    )

    with _client(monkeypatch) as client:
        resp = client.get("/api/portfolio/risk-lens", params={"session_id": _SESSION})

    assert resp.status_code == 200
    body = resp.json()
    assert body["priced_count"] == 0
    assert body["degraded"] is True
    # 成本价兜底：total_value 等于成本，但已由 degraded 标记。
    assert body["total_value"] == 1500.0
