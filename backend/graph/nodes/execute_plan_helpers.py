"""Pure helpers extracted from execute_plan_stub.

Keeps id/profile/score helper logic out of the large executor function
so execute_plan_stub stays focused on step scheduling and RAG bookkeeping.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timezone
from typing import Any

from backend.graph.json_utils import json_dumps_safe
from backend.graph.state import GraphState

def _env_int(name: str, default: int, *, min_value: int = 0, max_value: int = 10_000) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        parsed = int(str(raw).strip())
    except Exception:
        return default
    return max(min_value, min(max_value, parsed))


def _finite_float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return parsed if math.isfinite(parsed) else default


def _finite_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    parsed = _finite_float(value, math.nan)
    return parsed if math.isfinite(parsed) else None


def _ttl_hours_for_evidence(*, subject_type: str, evidence_type: str, source: str, confidence: float = 0.0, source_reliability: float = 0.0) -> int:
    """
    RAG v2 TTL policy:
    - filing/research_doc: persistent (no TTL)
    - DeepSearch high-quality (confidence >= 0.7 AND source_reliability >= 0.75): persistent
    - news/selection/search-derived: short-term TTL
    - others: session-ephemeral TTL
    """
    if subject_type in ("filing", "research_doc"):
        return 0

    confidence = _finite_float(confidence, 0.0)
    source_reliability = _finite_float(source_reliability, 0.0)

    # E4: DeepSearch high-quality results 鈫?persistent
    if confidence >= 0.7 and source_reliability >= 0.75:
        return 0

    news_ttl = _env_int("RAG_V2_NEWS_TTL_HOURS", 24 * 7, min_value=1, max_value=24 * 180)
    ephemeral_ttl = _env_int("RAG_V2_EPHEMERAL_TTL_HOURS", 12, min_value=1, max_value=24 * 30)

    source_norm = (source or "").strip().lower()
    evidence_type_norm = (evidence_type or "").strip().lower()
    if evidence_type_norm in ("news", "selection"):
        return news_ttl
    if source_norm in ("news", "selection", "search", "tavily", "exa", "google_news"):
        return news_ttl
    return ephemeral_ttl


# E4: High-reliability source domains (strict whitelist from deep_search_agent)
_HIGH_RELIABILITY_SOURCE_HINTS = frozenset({
    "sec.gov", "reuters.com", "bloomberg.com", "wsj.com", "ft.com",
})


def _estimate_source_reliability(url: str) -> float:
    """Estimate source reliability from URL domain (0.0 - 1.0)."""
    if not url:
        return 0.5
    url_lower = url.lower()
    # Check high-reliability domains
    for domain in _HIGH_RELIABILITY_SOURCE_HINTS:
        if domain in url_lower:
            return 0.9
    # Investor relations pages
    if "investor" in url_lower:
        return 0.85
    # Known finance sources
    finance_hints = ("yahoo.com/finance", "cnbc.com", "marketwatch.com", "seekingalpha.com")
    for hint in finance_hints:
        if hint in url_lower:
            return 0.75
    return 0.6


def _build_rag_doc_id(*, thread_id: str, evidence: dict[str, Any], index: int) -> str:
    explicit = str(evidence.get("id") or "").strip()
    if explicit:
        return explicit
    title = str(evidence.get("title") or "").strip()
    url = str(evidence.get("url") or "").strip()
    snippet = str(evidence.get("snippet") or "").strip()
    material = f"{thread_id}|{index}|{title}|{url}|{snippet}".encode("utf-8")
    return hashlib.sha1(material, usedforsecurity=False).hexdigest()[:24]


def _sanitize_collection_segment(value: str) -> str:
    import re

    text = (value or "").strip()
    if not text:
        return "unknown"
    normalized = re.sub(r"[^A-Za-z0-9._-]", "_", text)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or "unknown"


def _collection_from_thread_id(thread_id: str) -> str:
    raw = str(thread_id or "").strip()
    parts = raw.split(":")
    if len(parts) == 3:
        tenant, user, thread = (_sanitize_collection_segment(p) for p in parts)
        return f"session:{tenant}:{user}:{thread}"
    return f"session:{_sanitize_collection_segment(raw)}"


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    raw = str(value).strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return None


def _stable_id(prefix: str, *parts: Any, length: int = 24) -> str:
    material = "|".join(str(part or "") for part in parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha1(material, usedforsecurity=False).hexdigest()[:length]}"


def _resolve_session_id(state: GraphState) -> str:
    ui_context = state.get("ui_context") if isinstance(state.get("ui_context"), dict) else {}
    for candidate in (
        state.get("session_id"),
        ui_context.get("session_id"),
        state.get("thread_id"),
    ):
        value = str(candidate or "").strip()
        if value:
            return value
    return "unknown"


def _resolve_rag_user_id(state: GraphState, *, session_id: str) -> str:
    candidate = session_id or str(state.get("thread_id") or "").strip()
    try:
        from backend.graph.store import resolve_user_id

        value = str(resolve_user_id(candidate) or "").strip()
        if value:
            return value
    except Exception:
        pass

    parts = candidate.split(":")
    if len(parts) >= 2 and str(parts[1]).strip():
        return str(parts[1]).strip()
    return "anonymous"


def _build_rag_run_id(*, state: GraphState, session_id: str, query_text: str, started_at: datetime) -> str:
    direct = str(state.get("run_id") or "").strip()
    if direct:
        return direct
    trace = state.get("trace") if isinstance(state.get("trace"), dict) else {}
    runtime = trace.get("runtime") if isinstance(trace.get("runtime"), dict) else {}
    for candidate in (trace.get("run_id"), runtime.get("run_id")):
        value = str(candidate or "").strip()
        if value:
            return value
    return _stable_id("ragrun", session_id, query_text, started_at.isoformat())


def _build_source_doc_obs_id(*, run_id: str, source_id: str, title: str, url: str, index: int) -> str:
    return _stable_id("srcdoc", run_id, source_id, title, url, index)


def _build_chunk_record_id(*, run_id: str, source_doc_id: str, chunk_index: int, chunk_text: str) -> str:
    return _stable_id("chunk", run_id, source_doc_id, chunk_index, chunk_text)


def _build_vector_source_id(*, collection: str, source_id: str, chunk_index: int, chunk_text: str) -> str:
    return _stable_id("vec", collection, source_id, chunk_index, chunk_text)


def _infer_chunk_doc_type(*, evidence_type: str, source: str, title: str, subject_type: str) -> str:
    evidence_norm = str(evidence_type or "").strip().lower()
    source_norm = str(source or "").strip().lower()
    title_norm = str(title or "").strip().lower()
    subject_norm = str(subject_type or "").strip().lower()

    if any(token in title_norm for token in ("transcript", "earnings call", "conference call")):
        return "transcript"
    if evidence_norm in {"filing", "sec", "10-k", "10-q", "8-k"} or source_norm in {"sec_edgar", "sec"}:
        return "filing"
    if evidence_norm in {"news", "selection"}:
        return "news"
    if subject_norm == "research_doc" or "research" in evidence_norm or "research" in source_norm:
        return "research"
    return "web_page"


def _chunk_profile(doc_type: str) -> dict[str, int]:
    profiles = {
        "filing": {"max_chunk_size": 1000, "overlap": 200},
        "transcript": {"max_chunk_size": 800, "overlap": 100},
        "news": {"max_chunk_size": 2000, "overlap": 0},
        "research": {"max_chunk_size": 1200, "overlap": 200},
        "web_page": {"max_chunk_size": 1200, "overlap": 200},
        "table": {"max_chunk_size": 8000, "overlap": 0},
    }
    return profiles.get(doc_type, profiles["web_page"])


def _infer_chunk_strategy(*, doc_type: str, chunk_count: int, content: str) -> str:
    if doc_type == "table":
        return "preserve_table"
    if chunk_count <= 1 and doc_type in {"news", "web_page"} and len(content) <= 2000:
        return "preserve_short_doc"
    if doc_type == "filing":
        return "recursive_filing"
    if doc_type == "transcript":
        return "qa_recursive"
    if doc_type == "research":
        return "recursive_research"
    return "recursive_generic"


def _build_source_doc_content(evidence: dict[str, Any]) -> str:
    pieces: list[str] = []
    seen: set[str] = set()

    for raw_value in (
        evidence.get("title"),
        evidence.get("content"),
        evidence.get("body"),
        evidence.get("text"),
        evidence.get("transcript"),
        evidence.get("snippet"),
        evidence.get("summary"),
        evidence.get("description"),
    ):
        value = str(raw_value or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        pieces.append(value)
    return "\n\n".join(pieces).strip()


def _safe_event_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        try:
            return json.loads(json_dumps_safe(payload, ensure_ascii=False))
        except Exception:
            return {"raw": str(payload)}
    if isinstance(payload, list):
        try:
            return {"items": json.loads(json_dumps_safe(payload, ensure_ascii=False))}
        except Exception:
            return {"items": [str(item) for item in payload[:20]]}
    return {"value": str(payload)}


def _decorate_rag_hit(hit: dict[str, Any]) -> dict[str, Any]:
    result = dict(hit or {})
    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    for key in (
        "run_id",
        "source_doc_id",
        "chunk_id",
        "doc_type",
        "chunk_index",
        "total_chunks",
        "chunk_strategy",
        "chunk_size",
        "chunk_overlap",
    ):
        if key in metadata and key not in result:
            result[key] = metadata.get(key)
    if metadata.get("source_id") and "evidence_source_id" not in result:
        result["evidence_source_id"] = metadata.get("source_id")
    if result.get("source_id") and "vector_source_id" not in result:
        result["vector_source_id"] = result.get("source_id")
    return result
