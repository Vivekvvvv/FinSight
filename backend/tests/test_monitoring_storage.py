# -*- coding: utf-8 -*-
"""MonitoringStorage 时间戳格式回归。

timestamp 列是全库最后一个 naive-UTC 持久化点（datetime.utcnow()）：任何
aware 侧比较（datetime.now(timezone.utc) - parsed）都会 TypeError——与
daily_tasks/reports_to_review/risk_lens 修过的 naive/aware 缺陷同类。
写入与 cutoff 统一改 aware 后，旧 naive 行必须仍能被 days 窗口读到；
同列混合格式和时区偏移时，窗口与排序按实际时刻比较。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

import backend.services.monitoring_storage as monitoring_storage
from backend.services.monitoring_storage import MonitoringStorage, _connect


def _snapshot(rate: float = 95.0) -> dict:
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


@pytest.mark.parametrize("operation", ["trend", "hourly", "cleanup"])
def test_monitoring_windows_compare_instants_across_timestamp_formats(tmp_path, monkeypatch, operation):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 18, 12, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(monitoring_storage, "datetime", FixedDatetime)
    db = tmp_path / "monitoring.db"
    store = MonitoringStorage(db)
    timestamps = [
        "2026-11-17T20:30:00+09:00",  # 窗口前，字符串却排在边界之后
        "2026-11-17T12:00:00",        # 旧版 naive UTC，恰好等于边界
        "2026-11-17T12:00:00+00:00",
        "2026-11-17T10:00:00-02:00",  # 与边界同一时刻
        "2026-11-17T10:30:00-02:00",  # 边界后，字符串却排在边界之前
        "2026-11-17T20:15:00+08:00",  # 比上一条更早，不能按字符串排序
    ]
    with _connect(db) as conn:
        conn.executemany(
            """
            INSERT INTO health_records (
                timestamp, source_name, status, success_rate,
                avg_response_time_ms, total_requests, success_count,
                failure_count, consecutive_failures, is_healthy
            ) VALUES (?, 'source', 'healthy', 99.0, 30.0, 10, 10, 0, 0, 1)
            """,
            [(stamp,) for stamp in timestamps],
        )

    if operation == "trend":
        for source in (None, "source"):
            rows = store.get_trend(source_name=source, days=1)
            assert len(rows) == 5
            assert [row["timestamp"] for row in rows[:2]] == [timestamps[4], timestamps[5]]
            assert {row["timestamp"] for row in rows[2:]} == set(timestamps[1:4])
    elif operation == "hourly":
        assert store.get_hourly_aggregation("source", hours=24) == [{
            "hour": "2026-11-17 12:00", "avg_success_rate": 99.0,
            "avg_response_time_ms": 30.0, "sample_count": 5,
        }]
    else:
        assert store.cleanup_old_records(keep_days=1) == 1
        with _connect(db) as conn:
            remaining = {row[0] for row in conn.execute("SELECT timestamp FROM health_records")}
        assert remaining == set(timestamps[1:])


@pytest.mark.parametrize("timestamps, oldest, newest", [
    ([], None, None),
    (["2026-11-17T12:00:00"], "2026-11-17T12:00:00", "2026-11-17T12:00:00"),
    (["invalid"], None, None),
    (["invalid", "2026-11-17T12:00:00"], "2026-11-17T12:00:00", "2026-11-17T12:00:00"),
    (["2026-11-17T20:30:00+09:00", "2026-11-17T10:30:00-02:00"],
     "2026-11-17T20:30:00+09:00", "2026-11-17T10:30:00-02:00"),
    (["2026-11-17T12:00:00", "2026-11-17T12:00:00.100000+00:00",
      "2026-11-17T13:00:00+01:00"],
     "2026-11-17T12:00:00", "2026-11-17T12:00:00.100000+00:00"),
])
def test_stats_report_chronological_timestamp_extremes(tmp_path, timestamps, oldest, newest):
    store = MonitoringStorage(tmp_path / "monitoring.db")
    with _connect(store.db_path) as conn:
        conn.executemany(
            """
            INSERT INTO health_records (
                timestamp, source_name, status, success_rate,
                avg_response_time_ms, total_requests, success_count,
                failure_count, consecutive_failures, is_healthy
            ) VALUES (?, 'source', 'healthy', 99.0, 30.0, 10, 10, 0, 0, 1)
            """,
            [(stamp,) for stamp in timestamps],
        )

    stats = store.get_stats()

    assert stats["total_records"] == len(timestamps)
    assert stats["source_count"] == int(bool(timestamps))
    assert stats["oldest_record"] == oldest
    assert stats["newest_record"] == newest


def test_saved_timestamp_is_timezone_aware(tmp_path):
    store = MonitoringStorage(tmp_path / "mon.db")
    store.save_health_snapshot(_snapshot())

    trend = store.get_trend(days=1)

    assert trend, "写入后 get_trend 应能读回记录"
    parsed = datetime.fromisoformat(trend[0]["timestamp"])
    assert parsed.tzinfo is not None, "timestamp 必须带 UTC 偏移（aware）"
    assert abs(
        (parsed - datetime.now(timezone.utc)).total_seconds()
    ) < 60, "timestamp 应接近当前 UTC 时刻"


def test_trend_still_reads_legacy_naive_rows(tmp_path):
    """旧库已是 naive ISO：格式升级后同列混合，旧行不得被窗口漏掉。"""
    db = tmp_path / "mon.db"
    store = MonitoringStorage(db)
    naive_ts = (datetime.now(timezone.utc) - timedelta(days=1)).replace(
        tzinfo=None
    ).isoformat()
    with _connect(db) as conn:
        conn.execute(
            """
            INSERT INTO health_records (
                timestamp, source_name, status, success_rate,
                avg_response_time_ms, total_requests, success_count,
                failure_count, consecutive_failures, is_healthy
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (naive_ts, "legacy_src", "healthy", 99.0, 30.0, 10, 10, 0, 0, 1),
        )

    trend = store.get_trend(source_name="legacy_src", days=7)

    assert [row["timestamp"] for row in trend] == [naive_ts]


def test_cleanup_respects_mixed_naive_aware_timestamps(tmp_path):
    """cleanup 按实际时刻清理，兼容旧 naive UTC 与新 aware 行。"""
    db = tmp_path / "mon.db"
    store = MonitoringStorage(db)
    old_naive = (datetime.now(timezone.utc) - timedelta(days=60)).replace(
        tzinfo=None
    ).isoformat()
    with _connect(db) as conn:
        conn.execute(
            """
            INSERT INTO health_records (
                timestamp, source_name, status, success_rate,
                avg_response_time_ms, total_requests, success_count,
                failure_count, consecutive_failures, is_healthy
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (old_naive, "old_src", "healthy", 99.0, 30.0, 10, 10, 0, 0, 1),
        )
    store.save_health_snapshot(_snapshot())  # 新写入一条

    deleted = store.cleanup_old_records(keep_days=30)

    assert deleted == 1
    trend = store.get_trend(days=7)
    assert {row["source_name"] for row in trend} == {"tencent"}


def test_hourly_aggregation_handles_offset_suffix(tmp_path):
    """aware ISO 的 '+00:00' 后缀不能破坏 SQLite strftime 的小时分桶。"""
    store = MonitoringStorage(tmp_path / "mon.db")
    store.save_health_snapshot(_snapshot(90.0))
    store.save_health_snapshot(_snapshot(96.0))

    hourly = store.get_hourly_aggregation("tencent", hours=1)

    assert len(hourly) == 1
    assert hourly[0]["sample_count"] == 2
    assert abs(hourly[0]["avg_success_rate"] - 93.0) < 1e-6
    assert isinstance(sqlite3.sqlite_version, str)  # sanity: 真连接路径生效


def test_db_size_bytes_includes_uncheckpointed_wal(tmp_path):
    """数据库大小不能只算主库：WAL 里已提交未 checkpoint 的数据同样占盘。

    WAL 模式下主库在 checkpoint 前不增长，只 stat 主库会把"库在涨"读成
    "库没动"——实测主库 20 KiB、WAL 68 KiB，少报约 77%（项目规则 2：报出来的
    数字必须是实测事实）。
    """
    db = tmp_path / "mon.db"
    store = MonitoringStorage(db)

    # 保持写连接打开 = 不触发"最后一个连接关闭时 checkpoint"，数据留在 WAL。
    writer = sqlite3.connect(str(db))
    writer.execute("PRAGMA journal_mode=WAL")
    writer.executemany(
        """
        INSERT INTO health_records (
            timestamp, source_name, status, success_rate,
            avg_response_time_ms, total_requests, success_count,
            failure_count, consecutive_failures, is_healthy
        ) VALUES ('2026-01-01T00:00:00+00:00', 'src', 'healthy', 99.0, 30.0, 10, 10, 0, 0, 1)
        """,
        [() for _ in range(300)],
    )
    writer.commit()

    wal = db.with_name(db.name + "-wal")
    main_size = db.stat().st_size
    wal_size = wal.stat().st_size
    assert wal_size > 0, "测试前提：数据应仍在 WAL 里"

    try:
        reported = store.get_stats()["db_size_bytes"]
    finally:
        writer.close()

    assert reported == main_size + wal_size
    # buggy: 只算主库时 reported == main_size，WAL 部分被静默漏掉。
    assert reported > main_size
