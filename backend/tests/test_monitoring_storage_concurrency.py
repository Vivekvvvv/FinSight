# -*- coding: utf-8 -*-
"""R55 回归：MonitoringStorage 并发写读不因锁竞争 500。

单例 store 的写(save_health_snapshot)与读(get_trend/get_stats)并发时，
此前裸 sqlite3.connect（rollback journal + 5s 超时、无锁）会 database is
locked，读端点无 try/except 直接 500。加固为 WAL + busy_timeout + 进程锁。
"""
from __future__ import annotations

import threading

from backend.services.monitoring_storage import MonitoringStorage, _connect


def _snapshot(rate: float) -> dict:
    return {
        "tencent": {
            "status": "healthy",
            "success_rate": rate,
            "avg_response_time_ms": 42.0,
            "total_requests": 100,
            "success_count": 98,
            "failure_count": 2,
            "consecutive_failures": 0,
            "is_healthy": True,
        }
    }


def test_wal_mode_enabled(tmp_path):
    db = tmp_path / "mon.db"
    MonitoringStorage(db)  # 建库
    with _connect(db) as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert str(mode).lower() == "wal"


def test_concurrent_read_write_no_lock_error(tmp_path):
    store = MonitoringStorage(tmp_path / "mon.db")
    errors: list[Exception] = []

    def writer():
        try:
            for i in range(20):
                store.save_health_snapshot(_snapshot(90.0 + i))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    def reader():
        try:
            for _ in range(20):
                store.get_trend(days=7)
                store.get_stats()
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=writer) for _ in range(2)]
    threads += [threading.Thread(target=reader) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"并发读写抛错: {errors[:3]}"
