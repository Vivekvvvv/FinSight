# -*- coding: utf-8 -*-
"""组合摘要：库里解析不出的持仓行被跳过时，汇总不能装作组合是完整的。

`get_positions` 对 shares/avg_cost 非有限或非数字的存量行逐条 continue，
组合摘要把剩下的行加总后照常返回 success=True——用户看到的是"完整组合"，
少掉的仓位在 total_value/total_cost 里无声消失（项目规则 2）。
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.api.main import app
from backend.services import portfolio_store


def _insert_raw_position(session_id: str, ticker: str) -> None:
    with portfolio_store._db_lock, portfolio_store._connect() as conn:
        conn.execute(
            "INSERT INTO portfolio_positions "
            "(session_id, ticker, shares, avg_cost, updated_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, ticker, "not-a-number", 10.0, "2026-01-01T00:00:00+00:00"),
        )
        conn.commit()


def test_store_reports_invalid_rows_via_diagnostics():
    session_id = "public:anonymous:portfolio-invalid-store"
    portfolio_store.remove_position(session_id, "BADROW")
    _insert_raw_position(session_id, "BADROW")

    diagnostics: dict = {}
    try:
        positions = portfolio_store.get_positions(session_id, diagnostics=diagnostics)
    finally:
        portfolio_store.remove_position(session_id, "BADROW")

    assert positions == []
    assert diagnostics["invalid_positions"] == ["BADROW"]


def test_portfolio_summary_flags_dropped_positions():
    session_id = "public:anonymous:portfolio-invalid-summary"
    portfolio_store.remove_position(session_id, "BADROW")
    _insert_raw_position(session_id, "BADROW")

    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/portfolio/summary", params={"session_id": session_id}
            )
    finally:
        portfolio_store.remove_position(session_id, "BADROW")

    assert response.status_code == 200
    payload = response.json()
    assert payload["positions"] == []
    assert payload["invalid_positions"] == ["BADROW"]
    assert payload["degraded"] is True
    assert payload["fallback_reason"] == "invalid_stored_positions"


def test_portfolio_summary_stays_clean_without_invalid_rows():
    session_id = "public:anonymous:portfolio-clean-summary"
    portfolio_store.remove_position(session_id, "OKROW")
    portfolio_store.update_position(session_id=session_id, ticker="OKROW", shares=1, avg_cost=10)

    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/portfolio/summary", params={"session_id": session_id}
            )
    finally:
        portfolio_store.remove_position(session_id, "OKROW")

    assert response.status_code == 200
    payload = response.json()
    assert [p["ticker"] for p in payload["positions"]] == ["OKROW"]
    assert "invalid_positions" not in payload
    assert "degraded" not in payload
