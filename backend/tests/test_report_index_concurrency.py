# -*- coding: utf-8 -*-
"""R69 回归：ReportIndexStore 并发写读不因锁竞争故障，WAL 已启用。

report_index 是核心用户数据（报告索引）。读方法（list_reports 等）不持
self._lock，与写方法（upsert_report 大事务）并发时，此前裸连接会抛
database is locked，读端点故障。加固为 WAL + busy_timeout。
"""
from __future__ import annotations

import threading

import backend.services.report_index as ri


def _make_store(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORT_INDEX_SQLITE_PATH", str(tmp_path / "reports.db"))
    return ri.ReportIndexStore()


def _report(i: int) -> dict:
    return {
        "report_id": f"r{i}",
        "ticker": "AAPL",
        "title": f"Report {i}",
        "summary": "s",
        "confidence_score": 0.8,
        "generated_at": "2026-01-10T00:00:00+00:00",
    }


def test_wal_mode_enabled(tmp_path, monkeypatch):
    store = _make_store(tmp_path, monkeypatch)
    with store._connect() as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert str(mode).lower() == "wal"


def test_concurrent_read_write_no_lock_error(tmp_path, monkeypatch):
    store = _make_store(tmp_path, monkeypatch)
    errors: list[Exception] = []

    def writer():
        try:
            for i in range(20):
                store.upsert_report(session_id="private:u:default", report=_report(i))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    def reader():
        try:
            for _ in range(20):
                store.list_reports(session_id="private:u:default", limit=50)
                store.count_reports_since(session_id="private:u:default", since="2026-01-01T00:00:00+00:00")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=writer) for _ in range(2)]
    threads += [threading.Thread(target=reader) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"并发读写抛错: {errors[:3]}"
