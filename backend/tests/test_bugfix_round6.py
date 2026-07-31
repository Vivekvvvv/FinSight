# -*- coding: utf-8 -*-
"""Bug 审计（docs/BUG_AUDIT_2026-07-04.md）修复回归测试 —— B1 / B2 / C1 / D1 / D2。"""
from __future__ import annotations

import threading
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


# ── R14: 美股交易窗口被写成"北京时间的美股时段"误标 UTC ───────────────────────

def test_r14_us_trading_window_uses_real_utc_session():
    from backend.services.smart_cache import TradingHoursCache

    # 美股盘中：周二 15:00 UTC（= 11:00 ET 夏令时 / 10:00 ET 冬令时）
    in_session = datetime(2026, 7, 7, 15, 0, tzinfo=timezone.utc)
    assert TradingHoursCache._is_us_trading(in_session) is True  # 旧窗口 21:30-04:00 判 False

    # 美股收盘后：周二 22:30 UTC（= 18:30 ET，已收盘）
    after_hours = datetime(2026, 7, 7, 22, 30, tzinfo=timezone.utc)
    assert TradingHoursCache._is_us_trading(after_hours) is False  # 旧窗口误判 True

    # 开盘前：周二 12:00 UTC
    pre_market = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)
    assert TradingHoursCache._is_us_trading(pre_market) is False


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


def test_daily_risk_snapshot_session_error_log_is_redacted(monkeypatch, caplog):
    import backend.services.portfolio_store as portfolio_store
    import backend.services.risk_snapshot_scheduler as sched

    secret = "PRIVATE postgres://risk:secret@db/session"
    monkeypatch.setattr(sched, "get_all_active_sessions", lambda: [("private:alice:default", "alice")])
    monkeypatch.setattr(
        portfolio_store,
        "get_positions",
        lambda _session_id: (_ for _ in ()).throw(RuntimeError(secret)),
    )

    sched.take_daily_risk_snapshot()

    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_daily_risk_snapshot_job_error_log_is_redacted(monkeypatch, caplog):
    import backend.services.risk_snapshot_scheduler as sched

    secret = "PRIVATE postgres://risk:secret@db/job"

    def _fail_sessions():
        raise RuntimeError(secret)

    monkeypatch.setattr(sched, "get_all_active_sessions", _fail_sessions)

    sched.take_daily_risk_snapshot()

    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


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


# ── D2: 数据源健康指标全局单例无锁 → 并发计数丢失 ───────────────────────────────

def test_d2_concurrent_record_success_no_lost_updates():
    from backend.services.datasource_monitor import DataSourceMonitor

    mon = DataSourceMonitor()
    per_thread = 500
    n_threads = 4

    def worker():
        for _ in range(per_thread):
            mon.record_success("tencent", 1.0)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 修复前：无锁 `total_requests += 1` 在多线程下丢更新 → < 期望值
    assert mon._metrics["tencent"].total_requests == per_thread * n_threads
    assert mon._metrics["tencent"].success_count == per_thread * n_threads


# ── D1: SubscriptionService 读-改-写无锁 → 迭代时增删顶层 key 崩溃 ──────────────

def test_d1_concurrent_subscribe_and_iterate_no_crash(tmp_path, monkeypatch):
    from backend.services import subscription_service as subs

    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", tmp_path / "subs_concurrency.json")
    monkeypatch.setattr(subs, "_subscription_service", None, raising=False)
    svc = subs.SubscriptionService()
    # 聚焦内存数据结构并发安全，屏蔽磁盘 IO 以高频复现
    monkeypatch.setattr(svc, "_save_subscriptions", lambda: None)

    errors: list[Exception] = []

    def writer():
        try:
            for i in range(300):
                svc.subscribe(f"u{i}@example.com", "AAPL")
                svc.unsubscribe(f"u{i}@example.com")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    def reader():
        try:
            for _ in range(300):
                svc.get_subscriptions(allow_all=True)
                svc.get_subscribers_for_ticker("AAPL")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 修复前：reader 迭代 self.subscriptions 时 writer 增删顶层 key
    # → RuntimeError: dictionary changed size during iteration
    assert errors == []
