# -*- coding: utf-8 -*-
"""Portfolio Risk Lens Snapshots Storage

每日快照存储，用于历史趋势图展示。
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# 默认数据库路径
DEFAULT_DB_PATH = Path("./data/portfolio_risk_snapshots.db")


def _ensure_snapshots_table(db_path: Path = DEFAULT_DB_PATH) -> None:
    """确保快照表存在"""
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
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

    conn = sqlite3.connect(str(db_path))
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
            json.dumps(risk_lens_data, ensure_ascii=False),
            datetime.now(timezone.utc).isoformat(),
        ))
        conn.commit()
    finally:
        conn.close()


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

    conn = sqlite3.connect(str(db_path))
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
        return [dict(row) for row in reversed(rows)]
    finally:
        conn.close()


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

    conn = sqlite3.connect(str(db_path))
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

        return {
            "snapshot_date": row["snapshot_date"],
            "data": json.loads(row["full_data"]),
        }
    finally:
        conn.close()
