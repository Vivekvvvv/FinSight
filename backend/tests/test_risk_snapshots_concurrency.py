# -*- coding: utf-8 -*-
"""R56 回归：risk_snapshots 并发写读不因锁竞争故障，WAL 已启用。

读(get_risk_snapshots_history/get_latest_snapshot，risk_lens_router 用户触发)
与写(save_risk_snapshot，每日调度器)并发时，此前裸 sqlite3.connect 会
database is locked。加固为 WAL + busy_timeout。
"""
from __future__ import annotations

import threading

from backend.services import risk_snapshots as rs


def _risk_data(score: int) -> dict:
    return {
        "risk_score": score,
        "total_value": 100000.0,
        "total_cost": 90000.0,
        "concentration_risk": [{"x": 1}],
        "loss_positions": [],
        "stale_research": [],
        "missing_coverage": [],
    }


def test_wal_mode_enabled(tmp_path):
    db = tmp_path / "risk.db"
    rs.save_risk_snapshot("s", "u", _risk_data(50), db_path=db)
    with rs._connect(db) as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert str(mode).lower() == "wal"


def test_concurrent_read_write_no_lock_error(tmp_path):
    db = tmp_path / "risk.db"
    errors: list[Exception] = []

    def writer():
        try:
            for i in range(15):
                rs.save_risk_snapshot("s", "u", _risk_data(50 + i),
                                      snapshot_date=f"2026-01-{(i % 28) + 1:02d}", db_path=db)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    def reader():
        try:
            for _ in range(15):
                rs.get_risk_snapshots_history("s", "u", days=30, db_path=db)
                rs.get_latest_snapshot("s", "u", db_path=db)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=writer) for _ in range(2)]
    threads += [threading.Thread(target=reader) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"并发读写抛错: {errors[:3]}"
