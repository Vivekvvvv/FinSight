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

from backend.utils.quote import safe_float

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


def _finite_number(value: object, *, field: str, allow_none: bool = False) -> float | None:
    if value is None and allow_none:
        return None
    number = safe_float(value)
    if number is None:
        raise ValueError(f"{field} must be finite")
    return number


def _reject_non_finite_json(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _normalize_tags(value: object) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        return None
    return [tag.strip()[:64] for tag in value[:20] if isinstance(tag, str) and tag.strip()]


def _parse_stored_tags(value: object) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value, parse_constant=_reject_non_finite_json)
        if not isinstance(parsed, list):
            raise ValueError("tags must be a list")
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning("stored portfolio tags parse failed (%s)", type(exc).__name__)
        return []
    return _normalize_tags(parsed) or []


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
        try:
            shares = _finite_number(r[1], field="shares")
            avg_cost = _finite_number(r[2], field="avg_cost", allow_none=True)
        except ValueError as exc:
            logger.warning(
                "Skipping invalid stored portfolio position for ticker=%s (%s)",
                r[0],
                type(exc).__name__,
            )
            continue
        tags = _parse_stored_tags(r[5])
        result.append(
            {
                "ticker": r[0],
                "shares": shares,
                "avg_cost": avg_cost,
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
    """Replace all positions for *session_id* with the given list.

    sector/currency/opened_at 不在同步 payload 里（API 层不接收），
    全量替换时按 ticker 保留已有值，避免每次同步清空这三列。
    """
    now = datetime.now(timezone.utc).isoformat()
    with _db_lock, _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        preserved = {
            row[0]: (row[1], row[2], row[3])
            for row in db.execute(
                "SELECT ticker, sector, currency, opened_at FROM portfolio_positions WHERE session_id = ?",
                (session_id,),
            )
        }
        db.execute("DELETE FROM portfolio_positions WHERE session_id = ?", (session_id,))
        count = 0
        for pos in positions:
            ticker = str(pos.get("ticker", "")).strip().upper()
            if not ticker:
                continue
            shares = _finite_number(pos.get("shares", 0), field="shares")
            avg_cost = _finite_number(pos.get("avg_cost"), field="avg_cost", allow_none=True)
            name = str(pos.get("name") or "").strip() or None
            note = str(pos.get("note") or "").strip() or None
            tags = _normalize_tags(pos.get("tags"))
            tags_json = json.dumps(tags, ensure_ascii=False) if tags is not None else None
            prev_sector, prev_currency, prev_opened_at = preserved.get(ticker, (None, None, None))
            db.execute(
                "INSERT INTO portfolio_positions (session_id, ticker, shares, avg_cost, updated_at, name, tags_json, note, sector, currency, opened_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id, ticker, shares, avg_cost, now, name, tags_json, note,
                    pos.get("sector") or prev_sector,
                    pos.get("currency") or prev_currency or "USD",
                    pos.get("opened_at") or prev_opened_at,
                ),
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
    shares = _finite_number(shares, field="shares")
    avg_cost = _finite_number(avg_cost, field="avg_cost", allow_none=True)
    now = datetime.now(timezone.utc).isoformat()
    normalized_tags = _normalize_tags(tags)
    tags_json = json.dumps(normalized_tags, ensure_ascii=False) if normalized_tags is not None else None
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
            (
                suggestion_id,
                session_id,
                json.dumps(data, ensure_ascii=False, allow_nan=False),
                now,
                now,
            ),
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
            parsed = json.loads(r[1], parse_constant=_reject_non_finite_json)
            if not isinstance(parsed, dict):
                raise ValueError("suggestion payload must be an object")
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning(
                "stored rebalance suggestion parse failed for suggestion_id=%s: %s",
                r[0],
                type(exc).__name__,
            )
            parsed = {}
        result.append({
            "suggestion_id": r[0],
            "data": parsed,
            "status": r[2],
            "created_at": r[3],
            "updated_at": r[4],
        })
    return result


def patch_suggestion(suggestion_id: str, status: str, session_id: str | None = None) -> bool:
    now = datetime.now(timezone.utc).isoformat()
    with _db_lock, _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        # 传入 session_id 时追加属主过滤，防止仅凭 suggestion_id 改他人建议状态。
        if session_id:
            cursor = db.execute(
                "UPDATE rebalance_suggestions SET status = ?, updated_at = ? "
                "WHERE suggestion_id = ? AND session_id = ?",
                (status, now, suggestion_id, session_id),
            )
        else:
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
        user_id 从 session_id 解析：认证会话格式为 "private:{user_id}:default"
        （见 backend/security/auth.py Principal.session_id 与 graph/store.resolve_user_id），
        其余格式回退 "default_user"。
    """
    with _db_lock, _connect() as db:
        rows = db.execute(
            "SELECT DISTINCT session_id FROM portfolio_positions ORDER BY session_id"
        ).fetchall()

        result = []
        for row in rows:
            session_id = row[0]
            user_id = "default_user"
            parts = str(session_id or "").split(":")
            if len(parts) >= 2 and parts[1].strip():
                user_id = parts[1].strip()
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
