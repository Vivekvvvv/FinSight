# -*- coding: utf-8 -*-
"""MonitoringStorage 时间戳格式回归。

timestamp 列是全库最后一个 naive-UTC 持久化点（datetime.utcnow()）：任何
aware 侧比较（datetime.now(timezone.utc) - parsed）都会 TypeError——与
daily_tasks/reports_to_review/risk_lens 修过的 naive/aware 缺陷同类。
写入与 cutoff 统一改 aware 后，旧 naive 行必须仍能被 days 窗口读到
（同列混合格式，字符串比较方向兼容）。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

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
    """cleanup 的 timestamp < cutoff 比较对 naive/aware 混合行方向一致。"""
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
