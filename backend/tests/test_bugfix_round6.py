# -*- coding: utf-8 -*-
"""Bug 审计（docs/BUG_AUDIT_2026-07-04.md）修复回归测试 —— B1 / B2 / C1。"""
from __future__ import annotations

from datetime import datetime, timezone


# ── B1: smart_cache._is_cn_trading 的 datetime + int 必崩 ──────────────────────

def test_b1_is_cn_trading_no_typeerror_and_detects_session():
    from backend.services.smart_cache import TradingHoursCache

    # 北京时间周一 10:00 == UTC 02:00，处于 A股上午交易时段
    utc_in_session = datetime(2026, 1, 5, 2, 0, tzinfo=timezone.utc)
    # 修复前这行会抛 TypeError: datetime + int
    assert TradingHoursCache._is_cn_trading(utc_in_session) is True

    # 北京时间周一 16:00 == UTC 08:00，盘后
    utc_after_hours = datetime(2026, 1, 5, 8, 0, tzinfo=timezone.utc)
    assert TradingHoursCache._is_cn_trading(utc_after_hours) is False


def test_b1_get_smart_ttl_cn_returns_positive_int():
    from backend.services.smart_cache import TradingHoursCache

    ttl = TradingHoursCache.get_smart_ttl("cn", "quote")
    assert isinstance(ttl, int) and ttl > 0


# ── B2: 每日风险快照对 list 调 .get("items") → AttributeError 被吞，永不落库 ──

def test_b2_daily_risk_snapshot_saves_when_list_reports_returns_list(monkeypatch):
    import backend.services.risk_snapshot_scheduler as sched

    saved: list[tuple[str, str]] = []

    monkeypatch.setattr(
        sched, "get_all_active_sessions",
        lambda: [("private:alice:default", "alice")],
    )
    monkeypatch.setattr(
        "backend.services.portfolio_store.get_positions",
        lambda session_id: [{"ticker": "AAPL", "shares": 10}],
    )

    class _FakeStore:
        def list_reports(self, **kwargs):
            # 真实 ReportIndexStore.list_reports 返回 list[dict]，不是 {"items": [...]}
            return [{"report_id": "r1", "ticker": "AAPL"}]

    monkeypatch.setattr(
        "backend.services.report_index.get_report_index_store",
        lambda: _FakeStore(),
    )
    monkeypatch.setattr(sched, "calculate_portfolio_risk_lens", lambda pos, rep: {"risk_score": 50})
    monkeypatch.setattr(
        sched, "save_risk_snapshot",
        lambda session_id, user_id, lens, date: saved.append((session_id, user_id)),
    )

    sched.take_daily_risk_snapshot()

    # 修复前：.get("items") 在 list 上抛 AttributeError → per-session except 吞掉 → save 从不执行
    assert saved == [("private:alice:default", "alice")]


# ── C1: 待复查报告接口被 naive 日期 as_of 打成 TypeError → 500 ─────────────────

def test_c1_reports_to_review_handles_naive_as_of(monkeypatch):
    import backend.services.reports_to_review as rtr

    class _FakeStore:
        def list_reports(self, **kwargs):
            return [{
                "report_id": "r1",
                "ticker": "AAPL",
                "as_of": "2020-01-01",       # naive 纯日期串（财报/备案常见）
                "review_status": "done",
                "freshness_status": "live",
                "quality_state": "ok",
            }]

    monkeypatch.setattr(rtr, "get_report_index_store", lambda: _FakeStore())

    # 修复前：naive as_of < aware stale_threshold 抛 TypeError，未被 except 捕获 → 整体崩
    result = rtr.get_reports_to_review("sess", ["AAPL"], [], stale_days=7)
    assert isinstance(result, list)
    # 2020 年数据超期且 AAPL 在 watchlist → 命中规则4
    assert any(r.get("ticker") == "AAPL" for r in result)
