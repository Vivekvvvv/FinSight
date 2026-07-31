from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.demo_mode import demo_reports, is_demo_mode
from backend.security.auth import Principal, get_current_user, require_matching_identity

# 防御性校验: report_id 仅允许安全字符
_SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9._\-]{1,128}$")


def _validate_report_id(report_id: str) -> str:
    """校验 report_id 格式，防止注入或路径穿越。"""
    if not report_id or not _SAFE_ID_PATTERN.fullmatch(report_id):
        raise HTTPException(status_code=422, detail="report_id format invalid")
    return report_id


def _validate_iso_filter(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid date filter") from exc
    return text


@dataclass(frozen=True)
class ReportRouterDeps:
    resolve_thread_id: Callable[[Optional[str]], str]
    get_report_index_store: Callable[[], Any]


def create_report_router(deps: ReportRouterDeps) -> APIRouter:
    router = APIRouter(tags=["Reports"])

    @router.get("/api/reports/index")
    async def list_report_index(
        session_id: str,
        ticker: Optional[str] = Query(None, max_length=32),
        query: Optional[str] = Query(None, max_length=2048),
        date_from: Optional[str] = Query(None, max_length=32),
        date_to: Optional[str] = Query(None, max_length=32),
        tag: Optional[str] = Query(None, max_length=128),
        source_type: Optional[str] = Query(None, max_length=64),
        review_status: Optional[str] = Query(None, max_length=64),
        quality_state_filter: Optional[str] = Query(None, max_length=32),
        sort_by: str = Query("generated_at_desc", max_length=64),
        favorite_only: bool = False,
        include_blocked: bool = False,
        limit: int = Query(50, ge=1, le=500),
        current_user: Principal = Depends(get_current_user),
    ):
        require_matching_identity(
            principal=current_user,
            provided=session_id,
            expected=current_user.session_id,
            field_name="session_id",
        )
        try:
            normalized_session = deps.resolve_thread_id(session_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid session_id") from exc
        date_from = _validate_iso_filter(date_from)
        date_to = _validate_iso_filter(date_to)

        store = deps.get_report_index_store()
        rows = store.list_reports(
            session_id=normalized_session,
            ticker=ticker,
            query=query,
            date_from=date_from,
            date_to=date_to,
            tag=tag,
            source_type=source_type,
            review_status=review_status,
            quality_state_filter=quality_state_filter,
            sort_by=sort_by,
            favorite_only=bool(favorite_only),
            include_blocked=bool(include_blocked),
            limit=limit,
        )
        has_filtered_real_rows = False
        if not rows and not include_blocked:
            has_filtered_real_rows = bool(store.list_reports(
                session_id=normalized_session,
                ticker=ticker,
                query=query,
                date_from=date_from,
                date_to=date_to,
                tag=tag,
                source_type=source_type,
                review_status=review_status,
                quality_state_filter=quality_state_filter,
                sort_by=sort_by,
                favorite_only=bool(favorite_only),
                include_blocked=True,
                limit=1,
            ))
        if is_demo_mode() and not rows and not has_filtered_real_rows:
            rows = demo_reports(normalized_session, limit=limit)
        return {"success": True, "session_id": normalized_session, "items": rows, "count": len(rows)}

    @router.get("/api/reports/replay/{report_id}")
    async def get_report_replay(
        report_id: str,
        session_id: str,
        include_blocked: bool = False,
        current_user: Principal = Depends(get_current_user),
    ):
        report_id = _validate_report_id(report_id)
        require_matching_identity(
            principal=current_user,
            provided=session_id,
            expected=current_user.session_id,
            field_name="session_id",
        )
        try:
            normalized_session = deps.resolve_thread_id(session_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid session_id") from exc

        store = deps.get_report_index_store()
        replay = store.get_report_replay(
            session_id=normalized_session,
            report_id=report_id,
            include_blocked=bool(include_blocked),
        )
        if not replay:
            raise HTTPException(status_code=404, detail="report not found")
        return {"success": True, "session_id": normalized_session, **replay}

    @router.get("/api/reports/citations")
    async def list_report_citations(
        session_id: str,
        report_id: Optional[str] = Query(None, max_length=128),
        query: Optional[str] = Query(None, max_length=2048),
        source_id: Optional[str] = Query(None, max_length=256),
        date_from: Optional[str] = Query(None, max_length=32),
        date_to: Optional[str] = Query(None, max_length=32),
        limit: int = Query(100, ge=1, le=500),
        current_user: Principal = Depends(get_current_user),
    ):
        require_matching_identity(
            principal=current_user,
            provided=session_id,
            expected=current_user.session_id,
            field_name="session_id",
        )
        try:
            normalized_session = deps.resolve_thread_id(session_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid session_id") from exc
        date_from = _validate_iso_filter(date_from)
        date_to = _validate_iso_filter(date_to)
        if report_id is not None:
            report_id = _validate_report_id(report_id)

        store = deps.get_report_index_store()
        rows = store.list_citations(
            session_id=normalized_session,
            report_id=report_id,
            query=query,
            source_id=source_id,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        )
        return {
            "success": True,
            "session_id": normalized_session,
            "items": rows,
            "count": len(rows),
        }

    @router.post("/api/reports/{report_id}/favorite")
    async def set_report_favorite(
        report_id: str,
        request: dict,
        current_user: Principal = Depends(get_current_user),
    ):
        report_id = _validate_report_id(report_id)
        session_id = request.get("session_id")
        require_matching_identity(
            principal=current_user,
            provided=session_id,
            expected=current_user.session_id,
            field_name="session_id",
        )
        try:
            normalized_session = deps.resolve_thread_id(session_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid session_id") from exc

        raw_favorite = request.get("is_favorite", True)
        if not isinstance(raw_favorite, bool):
            raise HTTPException(status_code=422, detail="is_favorite must be a boolean")
        is_favorite = raw_favorite
        store = deps.get_report_index_store()
        ok = store.set_favorite(
            session_id=normalized_session,
            report_id=report_id,
            is_favorite=is_favorite,
        )
        if not ok:
            raise HTTPException(status_code=404, detail="report not found")

        return {
            "success": True,
            "session_id": normalized_session,
            "report_id": report_id,
            "is_favorite": is_favorite,
        }

    @router.patch("/api/reports/{report_id}/note")
    async def set_report_note(
        report_id: str,
        request: dict,
        current_user: Principal = Depends(get_current_user),
    ):
        report_id = _validate_report_id(report_id)
        session_id = request.get("session_id")
        require_matching_identity(
            principal=current_user,
            provided=session_id,
            expected=current_user.session_id,
            field_name="session_id",
        )
        try:
            normalized_session = deps.resolve_thread_id(session_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid session_id") from exc

        raw_note = request.get("user_note", request.get("note", ""))
        note_text = str(raw_note or "").strip()
        if len(note_text) > 2000:
            raise HTTPException(status_code=422, detail="user_note is too long")

        store = deps.get_report_index_store()
        try:
            saved_note = store.set_user_note(
                session_id=normalized_session,
                report_id=report_id,
                user_note=note_text,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="report not found") from exc

        return {
            "success": True,
            "session_id": normalized_session,
            "report_id": report_id,
            "user_note": saved_note,
        }

    # ------------------------------------------------------------------
    # GET /api/reports/compare — structural diff between two reports
    # ------------------------------------------------------------------

    @router.get("/api/reports/compare")
    async def compare_reports(
        session_id: str,
        id1: str,
        id2: str,
        include_blocked: bool = False,
        current_user: Principal = Depends(get_current_user),
    ):
        """Compare two reports and return structured differences."""
        id1 = _validate_report_id(id1)
        id2 = _validate_report_id(id2)
        require_matching_identity(
            principal=current_user,
            provided=session_id,
            expected=current_user.session_id,
            field_name="session_id",
        )
        try:
            normalized_session = deps.resolve_thread_id(session_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid session_id") from exc

        store = deps.get_report_index_store()
        report_a = store.get_report_replay(
            session_id=normalized_session,
            report_id=id1,
            include_blocked=bool(include_blocked),
        )
        report_b = store.get_report_replay(
            session_id=normalized_session,
            report_id=id2,
            include_blocked=bool(include_blocked),
        )
        if not report_a:
            raise HTTPException(status_code=404, detail=f"report {id1} not found")
        if not report_b:
            raise HTTPException(status_code=404, detail=f"report {id2} not found")

        # Build structured diff
        def _safe_get(d: dict, *keys: str, default: Any = None) -> Any:
            current = d
            for key in keys:
                if not isinstance(current, dict):
                    return default
                current = current.get(key, default)
            return current

        ra = report_a.get("report", {}) if isinstance(report_a.get("report"), dict) else {}
        rb = report_b.get("report", {}) if isinstance(report_b.get("report"), dict) else {}

        # Score changes
        score_a = _safe_get(ra, "confidence_score")
        score_b = _safe_get(rb, "confidence_score")
        score_delta = None
        if isinstance(score_a, (int, float)) and isinstance(score_b, (int, float)):
            score_delta = round(score_b - score_a, 4)

        # Sentiment changes
        sentiment_a = _safe_get(ra, "sentiment") or _safe_get(ra, "recommendation")
        sentiment_b = _safe_get(rb, "sentiment") or _safe_get(rb, "recommendation")

        # Risk changes
        risks_a = _safe_get(ra, "risks", default=[]) or []
        risks_b = _safe_get(rb, "risks", default=[]) or []
        risks_a_set = {str(r) for r in risks_a} if isinstance(risks_a, list) else set()
        risks_b_set = {str(r) for r in risks_b} if isinstance(risks_b, list) else set()

        # Summary / key metric changes
        summary_a = _safe_get(ra, "summary", default="")
        summary_b = _safe_get(rb, "summary", default="")

        return {
            "success": True,
            "session_id": normalized_session,
            "report_a": {"report_id": id1, "title": _safe_get(ra, "title"), "generated_at": _safe_get(ra, "generated_at"), "as_of": _safe_get(ra, "as_of"), "citation_count": len(report_a.get("citations") or [])},
            "report_b": {"report_id": id2, "title": _safe_get(rb, "title"), "generated_at": _safe_get(rb, "generated_at"), "as_of": _safe_get(rb, "as_of"), "citation_count": len(report_b.get("citations") or [])},
            "diff": {
                "confidence_score": {"a": score_a, "b": score_b, "delta": score_delta},
                "sentiment": {"a": sentiment_a, "b": sentiment_b, "changed": sentiment_a != sentiment_b},
                "risks": {
                    "added": sorted(risks_b_set - risks_a_set),
                    "removed": sorted(risks_a_set - risks_b_set),
                    "unchanged_count": len(risks_a_set & risks_b_set),
                },
                "summary": {"a": summary_a, "b": summary_b},
                "citation_count": {"a": len(report_a.get("citations") or []), "b": len(report_b.get("citations") or [])},
                "data_freshness": {"a": _safe_get(ra, "as_of"), "b": _safe_get(rb, "as_of")},
            },
        }

    # ------------------------------------------------------------------
    # PATCH /api/reports/{report_id}/review_status
    # PATCH /api/reports/{report_id}/tags
    # POST  /api/reports/{report_id}/viewed
    # GET   /api/reports/index (extended — supports sort_by, review_status)
    # ------------------------------------------------------------------

    @router.patch("/api/reports/{report_id}/review_status")
    async def set_report_review_status(
        report_id: str,
        request: dict,
        current_user: Principal = Depends(get_current_user),
    ):
        report_id = _validate_report_id(report_id)
        session_id = request.get("session_id")
        require_matching_identity(
            principal=current_user,
            provided=session_id,
            expected=current_user.session_id,
            field_name="session_id",
        )
        try:
            normalized_session = deps.resolve_thread_id(session_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid session_id") from exc

        raw_status = request.get("review_status", "new")
        if not isinstance(raw_status, str):
            raise HTTPException(status_code=422, detail="invalid review_status")
        status = raw_status.strip().lower()
        if status not in {"new", "reviewed", "watch", "archived"}:
            raise HTTPException(status_code=422, detail="invalid review_status")
        store = deps.get_report_index_store()
        ok = store.set_review_status(session_id=normalized_session, report_id=report_id, review_status=status)
        if not ok:
            raise HTTPException(status_code=404, detail="report not found")
        return {"success": True, "session_id": normalized_session, "report_id": report_id, "review_status": status}

    @router.patch("/api/reports/{report_id}/tags")
    async def set_report_tags(
        report_id: str,
        request: dict,
        current_user: Principal = Depends(get_current_user),
    ):
        report_id = _validate_report_id(report_id)
        session_id = request.get("session_id")
        require_matching_identity(
            principal=current_user,
            provided=session_id,
            expected=current_user.session_id,
            field_name="session_id",
        )
        try:
            normalized_session = deps.resolve_thread_id(session_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid session_id") from exc

        tags = request.get("tags") or []
        if not isinstance(tags, list):
            raise HTTPException(status_code=422, detail="tags must be a list")
        if len(tags) > 20:
            raise HTTPException(status_code=422, detail="too many tags")
        if any(not isinstance(tag, str) or len(tag.strip()) > 64 for tag in tags):
            raise HTTPException(status_code=422, detail="invalid tag")
        store = deps.get_report_index_store()
        ok = store.set_tags(session_id=normalized_session, report_id=report_id, tags=tags)
        if not ok:
            raise HTTPException(status_code=404, detail="report not found")
        return {"success": True, "session_id": normalized_session, "report_id": report_id, "tags": tags}

    @router.post("/api/reports/{report_id}/viewed")
    async def mark_report_viewed(
        report_id: str,
        request: dict,
        current_user: Principal = Depends(get_current_user),
    ):
        report_id = _validate_report_id(report_id)
        session_id = request.get("session_id")
        require_matching_identity(
            principal=current_user,
            provided=session_id,
            expected=current_user.session_id,
            field_name="session_id",
        )
        try:
            normalized_session = deps.resolve_thread_id(session_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid session_id") from exc
        store = deps.get_report_index_store()
        store.mark_viewed(session_id=normalized_session, report_id=report_id)
        return {"success": True}

    return router
