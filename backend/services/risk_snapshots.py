# -*- coding: utf-8 -*-
"""Portfolio Risk Lens Snapshots Storage

每日快照存储，用于历史趋势图展示。
"""
from __future__ import annotations

import functools
import json
import logging
import math
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from backend.utils.strict_json import json_loads_strict


logger = logging.getLogger(__name__)


def _reject_non_finite_json(value: str) -> None:
    raise ValueError(f"non-finite JSON value: {value}")

# 默认数据库路径
DEFAULT_DB_PATH = Path("./data/portfolio_risk_snapshots.db")

# 进程级串行化：仅 WAL + busy_timeout 不足以在建库并发（多连接同时
# PRAGMA journal_mode=WAL）+ 多 writer 下消除 "database is locked"（R56 的
# 加固不完整、全量下 flaky）。用 RLock 串行化全部快照 DB 访问，对齐
# MonitoringStorage(R55)/portfolio_store；读写量低，串行化无性能影响。
_lock = threading.RLock()


def _synchronized(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with _lock:
            return func(*args, **kwargs)

    return wrapper


def _connect(db_path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


@_synchronized
def _ensure_snapshots_table(db_path: Path = DEFAULT_DB_PATH) -> None:
    """确保快照表存在"""
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = _connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS risk_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            snapshot_date TEXT NOT NULL,
            risk_score INTEGER NOT NULL,
            total_value REAL,
            total_cost REAL,
            concentration_risk_count INTEGER DEFAULT 0,
            loss_positions_count INTEGER DEFAULT 0,
            stale_research_count INTEGER DEFAULT 0,
            missing_coverage_count INTEGER DEFAULT 0,
            full_data TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(session_id, user_id, snapshot_date)
        )
    """)

    # 创建索引加速查询
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_snapshots_session_date
        ON risk_snapshots(session_id, user_id, snapshot_date DESC)
    """)

    conn.commit()
    conn.close()


@_synchronized
def save_risk_snapshot(
    session_id: str,
    user_id: str,
    risk_lens_data: dict[str, Any],
    snapshot_date: Optional[str] = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> None:
    """保存风险快照

    Args:
        session_id: 会话 ID
        user_id: 用户 ID
        risk_lens_data: calculate_portfolio_risk_lens() 返回的完整数据
        snapshot_date: 快照日期（YYYY-MM-DD），默认今天
        db_path: 数据库路径
    """
    _ensure_snapshots_table(db_path)

    if snapshot_date is None:
        snapshot_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    conn = _connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT OR REPLACE INTO risk_snapshots (
                session_id, user_id, snapshot_date,
                risk_score, total_value, total_cost,
                concentration_risk_count, loss_positions_count,
                stale_research_count, missing_coverage_count,
                full_data, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session_id,
            user_id,
            snapshot_date,
            risk_lens_data.get("risk_score", 0),
            risk_lens_data.get("total_value"),
            risk_lens_data.get("total_cost"),
            len(risk_lens_data.get("concentration_risk", [])),
            len(risk_lens_data.get("loss_positions", [])),
            len(risk_lens_data.get("stale_research", [])),
            len(risk_lens_data.get("missing_coverage", [])),
            json.dumps(risk_lens_data, ensure_ascii=False, allow_nan=False),
            datetime.now(timezone.utc).isoformat(),
        ))
        conn.commit()
    finally:
        conn.close()


@_synchronized
def get_risk_snapshots_history(
    session_id: str,
    user_id: str,
    days: int = 30,
    db_path: Path = DEFAULT_DB_PATH,
) -> list[dict[str, Any]]:
    """获取历史快照

    Args:
        session_id: 会话 ID
        user_id: 用户 ID
        days: 返回最近 N 天的快照
        db_path: 数据库路径

    Returns:
        快照列表，按日期升序排列
    """
    _ensure_snapshots_table(db_path)

    conn = _connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT
                snapshot_date,
                risk_score,
                total_value,
                total_cost,
                concentration_risk_count,
                loss_positions_count,
                stale_research_count,
                missing_coverage_count,
                created_at
            FROM risk_snapshots
            WHERE session_id = ? AND user_id = ?
            ORDER BY snapshot_date DESC
            LIMIT ?
        """, (session_id, user_id, days))

        rows = cursor.fetchall()
        # 反转为升序（图表从左到右：过去 -> 现在）
        result: list[dict[str, Any]] = []
        for row in reversed(rows):
            try:
                for field in ("risk_score", "total_value", "total_cost"):
                    value = row[field]
                    if value is not None and not math.isfinite(float(value)):
                        raise ValueError(f"{field} must be finite")
            except (TypeError, ValueError) as exc:
                logger.warning('invalid stored risk snapshot summary')
                continue
            result.append(dict(row))
        return result
    finally:
        conn.close()


@_synchronized
def get_latest_snapshot(
    session_id: str,
    user_id: str,
    db_path: Path = DEFAULT_DB_PATH,
) -> Optional[dict[str, Any]]:
    """获取最新快照完整数据

    Args:
        session_id: 会话 ID
        user_id: 用户 ID
        db_path: 数据库路径

    Returns:
        最新快照的完整 risk_lens 数据，如果不存在返回 None
    """
    _ensure_snapshots_table(db_path)

    conn = _connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT full_data, snapshot_date
            FROM risk_snapshots
            WHERE session_id = ? AND user_id = ?
            ORDER BY snapshot_date DESC
            LIMIT 1
        """, (session_id, user_id))

        row = cursor.fetchone()
        if not row:
            return None

        try:
            data = json_loads_strict(row["full_data"])
            if not isinstance(data, dict):
                raise ValueError("snapshot payload must be an object")
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning('invalid stored risk snapshot')
            return None
        return {"snapshot_date": row["snapshot_date"], "data": data}
    finally:
        conn.close()
