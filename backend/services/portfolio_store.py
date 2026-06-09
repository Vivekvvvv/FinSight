# -*- coding: utf-8 -*-
"""
Independent portfolio storage (Gate-5).

Uses a dedicated SQLite database ``data/portfolio.db`` — intentionally
separated from the LangGraph checkpointer DB to avoid lock contention
and migration coupling.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DB_DIR = Path(os.getenv("FINSIGHT_DATA_DIR", "data"))
_DB_PATH = _DB_DIR / "portfolio.db"


def _get_conn() -> sqlite3.Connection:
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), timeout=30, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def _ensure_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS portfolio_positions (
            session_id  TEXT NOT NULL,
            ticker      TEXT NOT NULL,
            shares      REAL NOT NULL,
            avg_cost    REAL,
            updated_at  TEXT NOT NULL,
            PRIMARY KEY (session_id, ticker)
        );

        CREATE TABLE IF NOT EXISTS rebalance_suggestions (
            suggestion_id TEXT PRIMARY KEY,
            session_id    TEXT NOT NULL,
            data          TEXT NOT NULL,
            status        TEXT NOT NULL DEFAULT 'draft',
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_rebalance_session
            ON rebalance_suggestions(session_id, created_at DESC);
    """)
    # Backwards-compatible column additions for 留存升级 (name/tags/note).
    existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(portfolio_positions)")}
    if "name" not in existing_columns:
        conn.execute("ALTER TABLE portfolio_positions ADD COLUMN name TEXT")
    if "tags_json" not in existing_columns:
        conn.execute("ALTER TABLE portfolio_positions ADD COLUMN tags_json TEXT")
    if "note" not in existing_columns:
        conn.execute("ALTER TABLE portfolio_positions ADD COLUMN note TEXT")
    # Phase 3: Today Workspace 字段扩展
    if "sector" not in existing_columns:
        conn.execute("ALTER TABLE portfolio_positions ADD COLUMN sector TEXT")
    if "currency" not in existing_columns:
        conn.execute("ALTER TABLE portfolio_positions ADD COLUMN currency TEXT DEFAULT 'USD'")
    if "opened_at" not in existing_columns:
        conn.execute("ALTER TABLE portfolio_positions ADD COLUMN opened_at TEXT")
    conn.commit()


_db_lock = threading.RLock()


def _connect() -> sqlite3.Connection:
    conn = _get_conn()
    _ensure_tables(conn)
    return conn


# ── Portfolio positions CRUD ────────────────────────────────


def get_positions(session_id: str) -> list[dict[str, Any]]:
    with _db_lock, _connect() as conn:
        rows = conn.execute(
            "SELECT ticker, shares, avg_cost, updated_at, name, tags_json, note, "
            "sector, currency, opened_at "
            "FROM portfolio_positions WHERE session_id = ? ORDER BY ticker",
            (session_id,),
        ).fetchall()
    result: list[dict[str, Any]] = []
    for r in rows:
        tags: list[str] = []
        raw_tags = r[5]
        if raw_tags:
            try:
                parsed = json.loads(raw_tags)
                if isinstance(parsed, list):
                    tags = [str(t) for t in parsed if str(t).strip()]
            except json.JSONDecodeError:
                tags = []
        result.append(
            {
                "ticker": r[0],
                "shares": r[1],
                "avg_cost": r[2],
                "updated_at": r[3],
                "name": r[4],
                "tags": tags,
                "note": r[6],
                "sector": r[7],
                "currency": r[8] or "USD",
                "opened_at": r[9],
            }
        )
    return result


def sync_positions(session_id: str, positions: list[dict[str, Any]]) -> int:
    """Replace all positions for *session_id* with the given list."""
    now = datetime.now(timezone.utc).isoformat()
    with _db_lock, _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM portfolio_positions WHERE session_id = ?", (session_id,))
        count = 0
        for pos in positions:
            ticker = str(pos.get("ticker", "")).strip().upper()
            if not ticker:
                continue
            name = str(pos.get("name") or "").strip() or None
            note = str(pos.get("note") or "").strip() or None
            tags = pos.get("tags")
            tags_json = json.dumps(tags, ensure_ascii=False) if isinstance(tags, list) else None
            db.execute(
                "INSERT INTO portfolio_positions (session_id, ticker, shares, avg_cost, updated_at, name, tags_json, note) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (session_id, ticker, float(pos.get("shares", 0)), pos.get("avg_cost"), now, name, tags_json, note),
            )
            count += 1
        db.commit()
    return count


def update_position(
    session_id: str,
    ticker: str,
    shares: float,
    avg_cost: float | None = None,
    *,
    name: str | None = None,
    tags: list[str] | None = None,
    note: str | None = None,
    sector: str | None = None,
    currency: str | None = None,
    opened_at: str | None = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    tags_json = json.dumps(tags, ensure_ascii=False) if isinstance(tags, list) else None
    with _db_lock, _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            """INSERT INTO portfolio_positions (session_id, ticker, shares, avg_cost, updated_at, name, tags_json, note, sector, currency, opened_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(session_id, ticker) DO UPDATE SET
                 shares=excluded.shares,
                 avg_cost=excluded.avg_cost,
                 updated_at=excluded.updated_at,
                 name=COALESCE(excluded.name, portfolio_positions.name),
                 tags_json=COALESCE(excluded.tags_json, portfolio_positions.tags_json),
                 note=COALESCE(excluded.note, portfolio_positions.note),
                 sector=COALESCE(excluded.sector, portfolio_positions.sector),
                 currency=COALESCE(excluded.currency, portfolio_positions.currency),
                 opened_at=COALESCE(excluded.opened_at, portfolio_positions.opened_at)""",
            (session_id, ticker.upper(), shares, avg_cost, now, name, tags_json, note, sector, currency or "USD", opened_at),
        )
        db.commit()

def remove_position(session_id: str, ticker: str) -> None:
    with _db_lock, _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "DELETE FROM portfolio_positions WHERE session_id = ? AND ticker = ?",
            (session_id, ticker.upper()),
        )
        db.commit()

# ── Rebalance suggestions CRUD ──────────────────────────────


def save_suggestion(suggestion_id: str, session_id: str, data: dict[str, Any]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _db_lock, _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            """INSERT INTO rebalance_suggestions (suggestion_id, session_id, data, status, created_at, updated_at)
               VALUES (?, ?, ?, 'draft', ?, ?)
               ON CONFLICT(suggestion_id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at""",
            (suggestion_id, session_id, json.dumps(data, ensure_ascii=False), now, now),
        )
        db.commit()


def list_suggestions(session_id: str, limit: int = 10) -> list[dict[str, Any]]:
    with _db_lock, _connect() as db:
        rows = db.execute(
            "SELECT suggestion_id, data, status, created_at, updated_at FROM rebalance_suggestions WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    result: list[dict[str, Any]] = []
    for r in rows:
        try:
            parsed = json.loads(r[1])
        except json.JSONDecodeError:
            parsed = {}
        result.append({
            "suggestion_id": r[0],
            "data": parsed,
            "status": r[2],
            "created_at": r[3],
            "updated_at": r[4],
        })
    return result


def patch_suggestion(suggestion_id: str, status: str) -> bool:
    now = datetime.now(timezone.utc).isoformat()
    with _db_lock, _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        cursor = db.execute(
            "UPDATE rebalance_suggestions SET status = ?, updated_at = ? WHERE suggestion_id = ?",
            (status, now, suggestion_id),
        )
        db.commit()
        return cursor.rowcount > 0


def get_all_active_sessions() -> list[tuple[str, str]]:
    """获取所有有持仓数据的会话

    Returns:
        [(session_id, user_id), ...] 列表
        注意：user_id 从 session_id 提取（假设格式为 "user_xxx" 或使用 "default_user"）
    """
    with _db_lock, _connect() as db:
        rows = db.execute(
            "SELECT DISTINCT session_id FROM portfolio_positions ORDER BY session_id"
        ).fetchall()

        result = []
        for row in rows:
            session_id = row[0]
            # 简化：从 session_id 推断 user_id
            # 实际生产环境应该有 user_id 列或从其他表关联
            user_id = "default_user"  # fallback
            if "_" in session_id:
                parts = session_id.split("_")
                if len(parts) >= 2:
                    user_id = parts[0]
            result.append((session_id, user_id))

        return result


__all__ = [
    "get_positions",
    "sync_positions",
    "update_position",
    "remove_position",
    "save_suggestion",
    "list_suggestions",
    "patch_suggestion",
    "get_all_active_sessions",
]
