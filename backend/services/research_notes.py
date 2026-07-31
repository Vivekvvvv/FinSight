# -*- coding: utf-8 -*-
"""Research Notes Storage Service

为每个 ticker 提供独立的研究笔记本，支持 Markdown 和图片。
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# 数据库路径
_DB_PATH = Path("./data/research_notes.db")
_db_lock = threading.RLock()
logger = logging.getLogger(__name__)


def _parse_tags(value: object) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        if not isinstance(parsed, list):
            raise ValueError("tags must be a list")
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning("invalid stored research note tags (%s)", type(exc).__name__)
        return []
    return [tag.strip()[:64] for tag in parsed[:20] if isinstance(tag, str) and tag.strip()]


def _get_conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), timeout=30, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def _ensure_tables(conn: sqlite3.Connection) -> None:
    """确保笔记表存在"""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS research_notes (
            note_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            ticker TEXT,
            title TEXT NOT NULL,
            content TEXT DEFAULT '',
            tags_json TEXT DEFAULT '[]',
            deleted INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_notes_session_ticker
            ON research_notes(session_id, ticker, updated_at DESC)
            WHERE deleted = 0;

        CREATE INDEX IF NOT EXISTS idx_notes_user
            ON research_notes(user_id, updated_at DESC)
            WHERE deleted = 0;
    """)


def _connect() -> sqlite3.Connection:
    conn = _get_conn()
    _ensure_tables(conn)
    return conn


def _close_all_connections():
    """关闭所有数据库连接（用于测试清理）"""
    # SQLite 不需要显式关闭连接池，context manager 会自动关闭
    pass


def create_note(
    session_id: str,
    user_id: str,
    title: str,
    content: str = "",
    ticker: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> str:
    """创建笔记

    Args:
        session_id: 会话 ID
        user_id: 用户 ID
        title: 笔记标题
        content: Markdown 内容
        ticker: 关联标的（可选）
        tags: 标签列表

    Returns:
        note_id
    """
    note_id = f"note_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    tags_json = json.dumps(tags or [], ensure_ascii=False)

    with _db_lock, _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("""
            INSERT INTO research_notes (
                note_id, session_id, user_id, ticker,
                title, content, tags_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            note_id, session_id, user_id, ticker,
            title, content, tags_json,
            now, now
        ))
        conn.commit()

    # 异步向量化（失败不影响主流程）
    try:
        from backend.services.notes_rag import vectorize_note as _vn
        _vn(note_id, title, content or "")
    except Exception as exc:
        logger.warning("note vectorization failed for %s: %s", note_id, type(exc).__name__)

    return note_id


def update_note(
    note_id: str,
    title: Optional[str] = None,
    content: Optional[str] = None,
    tags: Optional[list[str]] = None,
    ticker: Optional[str] = None,
) -> bool:
    """更新笔记

    Args:
        note_id: 笔记 ID
        title: 新标题（可选）
        content: 新内容（可选）
        tags: 新标签列表（可选）
        ticker: 新关联标的（可选）

    Returns:
        更新是否成功
    """
    now = datetime.now(timezone.utc).isoformat()
    updates = []
    params = []

    if title is not None:
        updates.append("title = ?")
        params.append(title)

    if content is not None:
        updates.append("content = ?")
        params.append(content)

    if tags is not None:
        updates.append("tags_json = ?")
        params.append(json.dumps(tags, ensure_ascii=False))

    if ticker is not None:
        updates.append("ticker = ?")
        params.append(ticker)

    if not updates:
        return False

    updates.append("updated_at = ?")
    params.append(now)
    params.append(note_id)

    with _db_lock, _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.execute(
            f"UPDATE research_notes SET {', '.join(updates)} WHERE note_id = ? AND deleted = 0",
            params
        )
        conn.commit()
        updated = cursor.rowcount > 0

    # 重新向量化（失败不影响主流程）
    if updated:
        try:
            note = get_note(note_id)
            if note:
                from backend.services.notes_rag import vectorize_note as _vn
                _vn(note_id, note.get("title", ""), note.get("content", ""))
        except Exception as exc:
            logger.warning("note re-vectorization failed for %s: %s", note_id, type(exc).__name__)

    return updated


def delete_note(note_id: str) -> bool:
    """删除笔记（软删除）

    Args:
        note_id: 笔记 ID

    Returns:
        删除是否成功
    """
    now = datetime.now(timezone.utc).isoformat()

    with _db_lock, _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.execute(
            "UPDATE research_notes SET deleted = 1, updated_at = ? WHERE note_id = ? AND deleted = 0",
            (now, note_id)
        )
        conn.commit()
        return cursor.rowcount > 0


def get_note(note_id: str) -> Optional[dict[str, Any]]:
    """获取单条笔记

    Args:
        note_id: 笔记 ID

    Returns:
        笔记字典，如果不存在返回 None
    """
    with _db_lock, _connect() as conn:
        row = conn.execute("""
            SELECT note_id, session_id, user_id, ticker,
                   title, content, tags_json,
                   created_at, updated_at
            FROM research_notes
            WHERE note_id = ? AND deleted = 0
        """, (note_id,)).fetchone()

        if not row:
            return None

        return {
            "note_id": row[0],
            "session_id": row[1],
            "user_id": row[2],
            "ticker": row[3],
            "title": row[4],
            "content": row[5],
            "tags": _parse_tags(row[6]),
            "created_at": row[7],
            "updated_at": row[8],
        }


def list_notes(
    session_id: str,
    user_id: str,
    ticker: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """列出笔记

    Args:
        session_id: 会话 ID
        user_id: 用户 ID
        ticker: 筛选标的（可选）
        limit: 返回数量限制
        offset: 偏移量

    Returns:
        笔记列表（按更新时间倒序）
    """
    with _db_lock, _connect() as conn:
        if ticker:
            rows = conn.execute("""
                SELECT note_id, session_id, user_id, ticker,
                       title, content, tags_json,
                       created_at, updated_at
                FROM research_notes
                WHERE session_id = ? AND user_id = ? AND ticker = ? AND deleted = 0
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?
            """, (session_id, user_id, ticker, limit, offset)).fetchall()
        else:
            rows = conn.execute("""
                SELECT note_id, session_id, user_id, ticker,
                       title, content, tags_json,
                       created_at, updated_at
                FROM research_notes
                WHERE session_id = ? AND user_id = ? AND deleted = 0
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?
            """, (session_id, user_id, limit, offset)).fetchall()

        result = []
        for row in rows:
            result.append({
                "note_id": row[0],
                "session_id": row[1],
                "user_id": row[2],
                "ticker": row[3],
                "title": row[4],
                "content": row[5],
                "tags": _parse_tags(row[6]),
                "created_at": row[7],
                "updated_at": row[8],
            })

        return result


def search_notes(
    session_id: str,
    user_id: str,
    query: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """搜索笔记（标题和内容）

    Args:
        session_id: 会话 ID
        user_id: 用户 ID
        query: 搜索关键词
        limit: 返回数量限制

    Returns:
        匹配的笔记列表
    """
    search_pattern = f"%{query}%"

    with _db_lock, _connect() as conn:
        rows = conn.execute("""
            SELECT note_id, session_id, user_id, ticker,
                   title, content, tags_json,
                   created_at, updated_at
            FROM research_notes
            WHERE session_id = ? AND user_id = ?
              AND deleted = 0
              AND (title LIKE ? OR content LIKE ?)
            ORDER BY updated_at DESC
            LIMIT ?
        """, (session_id, user_id, search_pattern, search_pattern, limit)).fetchall()

        result = []
        for row in rows:
            result.append({
                "note_id": row[0],
                "session_id": row[1],
                "user_id": row[2],
                "ticker": row[3],
                "title": row[4],
                "content": row[5],
                "tags": _parse_tags(row[6]),
                "created_at": row[7],
                "updated_at": row[8],
            })

        return result


__all__ = [
    "create_note",
    "update_note",
    "delete_note",
    "get_note",
    "list_notes",
    "search_notes",
]
