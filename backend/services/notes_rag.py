# -*- coding: utf-8 -*-
"""
研究笔记 RAG 向量化与语义搜索

使用现有 EmbeddingService，将笔记内容向量化存入 SQLite，
支持余弦相似度语义检索。EmbeddingService 不可用时降级为关键词搜索。
"""
from __future__ import annotations

import json
import logging
import math
import sqlite3
import threading
from pathlib import Path
from typing import Any

from backend.utils.strict_json import json_loads_strict

logger = logging.getLogger(__name__)

# 必须与 research_notes.py 的 _DB_PATH 指向同一个文件：
# _vector_search / vectorize_all_notes 会跨 notes_vectors 与 research_notes 两表 JOIN。
_DB_PATH = Path("./data/research_notes.db")
_lock = threading.RLock()


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def _conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(_DB_PATH), timeout=30, isolation_level=None)
    c.execute("PRAGMA journal_mode=WAL")
    return c


def _ensure_table() -> None:
    with _lock, _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS notes_vectors (
                note_id   TEXT PRIMARY KEY,
                vector_json TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
        """)


_table_ready = False

def _init() -> None:
    global _table_ready
    if not _table_ready:
        _ensure_table()
        _table_ready = True


# ── 嵌入工具 ──────────────────────────────────────────────────────────────────

def _get_embedder():
    try:
        from backend.rag.embedder import get_embedding_service
        return get_embedding_service()
    except Exception as exc:
        logger.debug("embedding service unavailable: %s", type(exc).__name__)
        return None


def _embed(text: str) -> list[float] | None:
    embedder = _get_embedder()
    if not embedder:
        return None
    try:
        result = embedder.embed_texts([text])
        vecs = result.dense
        if vecs and vecs[0]:
            vector = [float(value) for value in vecs[0]]
            if vector and all(math.isfinite(value) for value in vector):
                return vector
            logger.warning("embedding service returned a non-finite vector")
    except Exception as e:
        logger.debug("embed failed: %s", type(e).__name__)
    return None


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


# ── 公共接口 ──────────────────────────────────────────────────────────────────

def vectorize_note(note_id: str, title: str, content: str) -> bool:
    """生成笔记向量并存储，失败时静默返回 False"""
    _init()
    text = f"{title}\n{content}".strip()
    vec = _embed(text)
    if vec is None:
        return False
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        with _lock, _conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO notes_vectors(note_id, vector_json, updated_at) VALUES(?,?,?)",
                (note_id, json.dumps(vec), now)
            )
        return True
    except Exception as e:
        logger.warning("vectorize_note failed %s: %s", note_id, type(e).__name__)
        return False


def semantic_search_notes(
    session_id: str,
    user_id: str,
    query: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    语义搜索笔记。EmbeddingService 不可用时降级为关键词搜索。
    """
    _init()

    # 尝试向量语义搜索
    q_vec = _embed(query)
    if q_vec is not None:
        return _vector_search(session_id, user_id, q_vec, limit)

    # 降级：关键词搜索
    from backend.services.research_notes import search_notes
    return search_notes(session_id=session_id, user_id=user_id, query=query, limit=limit)


def _vector_search(
    session_id: str,
    user_id: str,
    q_vec: list[float],
    limit: int,
) -> list[dict[str, Any]]:
    # 拉出所有该用户未删除的笔记向量
    with _lock, _conn() as c:
        rows = c.execute("""
            SELECT nv.note_id, nv.vector_json,
                   rn.title, rn.content, rn.ticker, rn.tags_json,
                   rn.created_at, rn.updated_at
            FROM notes_vectors nv
            JOIN research_notes rn ON rn.note_id = nv.note_id
            WHERE rn.session_id = ? AND rn.user_id = ? AND rn.deleted = 0
        """, (session_id, user_id)).fetchall()

    if not rows:
        return []

    scored: list[tuple[float, dict]] = []
    for row in rows:
        note_id, vec_json, title, content, ticker, tags_json, created_at, updated_at = row
        try:
            doc_vec = json_loads_strict(vec_json)
            score = _cosine(q_vec, doc_vec)
            if not math.isfinite(score):
                raise ValueError("non-finite similarity")
        except Exception as exc:
            logger.warning("invalid stored note vector (%s)", type(exc).__name__)
            score = 0.0
        try:
            tags = json_loads_strict(tags_json or "[]")
            if not isinstance(tags, list):
                raise ValueError("tags must be a list")
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning("invalid stored note tags (%s)", type(exc).__name__)
            tags = []
        scored.append((score, {
            "note_id": note_id,
            "title": title,
            "content": content,
            "ticker": ticker,
            "tags": tags,
            "created_at": created_at,
            "updated_at": updated_at,
            "similarity": round(score, 4),
        }))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:limit]]


def vectorize_all_notes(session_id: str, user_id: str) -> dict[str, int]:
    """批量向量化所有未向量化的笔记，返回统计"""
    _init()
    with _lock, _conn() as c:
        rows = c.execute("""
            SELECT rn.note_id, rn.title, rn.content
            FROM research_notes rn
            LEFT JOIN notes_vectors nv ON nv.note_id = rn.note_id
            WHERE rn.session_id = ? AND rn.user_id = ? AND rn.deleted = 0
              AND nv.note_id IS NULL
        """, (session_id, user_id)).fetchall()

    ok = failed = 0
    for note_id, title, content in rows:
        if vectorize_note(note_id, title or "", content or ""):
            ok += 1
        else:
            failed += 1
    return {"vectorized": ok, "failed": failed, "total": len(rows)}
