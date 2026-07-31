from __future__ import annotations

import logging
import time as _time
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time
from typing import Any, Awaitable, Callable, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse

from backend.api.schemas import ChatRequest, ChartDataResponse
from backend.graph.confirmation_policy import parse_confirmation_mode
from backend.report.quality_engine import apply_quality_to_report, record_quality_metrics
from backend.security.auth import Principal, get_current_user, require_matching_identity
from backend.services.entitlements import enforce_feature


@dataclass(frozen=True)
class ChatRouterDeps:
    get_graph_runner: Callable[[], Awaitable[Any]]
    resolve_thread_id: Callable[[Optional[str]], str]
    build_ui_context: Callable[[ChatRequest], dict[str, Any]]
    resolve_query_reference: Callable[[str, str], str]
    schedule_report_index: Callable[..., None]
    update_session_context: Callable[..., None]
    contract_info: Callable[[], dict[str, str]]
    resolve_trace_raw_enabled: Callable[[ChatRequest], bool]
    is_raw_trace_event: Callable[[dict[str, Any]], bool]
    redact_sensitive_payload: Callable[[Any], Any]
    get_session_context: Callable[[str], Any]
    chat_history_store: Any | None
    chat_response_schema_version: str
    sse_event_schema_version: str


def create_chat_router(deps: ChatRouterDeps) -> APIRouter:
    router = APIRouter(tags=["Chat"])
    _logger = logging.getLogger("chat_router")
    _MAX_CHART_TICKER_CHARS = 64
    _MAX_CHART_SUMMARY_CHARS = 16_384

    @router.post("/chat/supervisor")
    async def chat_supervisor_endpoint(
        request: ChatRequest,
        http_request: Request,
        current_user: Principal = Depends(get_current_user),
    ):
        require_matching_identity(
            principal=current_user,
            provided=request.session_id,
            expected=current_user.session_id,
            field_name="session_id",
        )
        resolved_session_id = (
            request.session_id if current_user.auth_type == "dev" else current_user.session_id
        )
        _t0 = _time.perf_counter()
        try:
            runner = await deps.get_graph_runner()
            try:
                thread_id = deps.resolve_thread_id(resolved_session_id)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail="Invalid session_id") from exc

            ui_context = deps.build_ui_context(request)

            output_mode = None
            strict_selection = None
            confirmation_mode = None
            if getattr(request, "options", None):
                output_mode = request.options.output_mode
                strict_selection = request.options.strict_selection
                confirmation_mode = parse_confirmation_mode(request.options.confirmation_mode)

            # Chat entry point defaults to skip — Chat UI has no InterruptCard.
            # Exception: investment_report mode always requires confirmation (auto).
            if str(output_mode or "").strip().lower() == "investment_report":
                enforce_feature(getattr(http_request.state, "principal", None), "deep_research")

            if confirmation_mode is None:
                if str(output_mode or "").strip().lower() == "investment_report":
                    confirmation_mode = "auto"
                else:
                    confirmation_mode = "skip"

            resolved_query = deps.resolve_query_reference(request.query, thread_id)

            from backend.graph.runner import run_graph_traced
            state = await run_graph_traced(
                runner,
                thread_id=thread_id,
                query=resolved_query,
                ui_context=ui_context,
                output_mode=output_mode,
                strict_selection=strict_selection,
                confirmation_mode=confirmation_mode,
            )
            markdown = ((state.get("artifacts") or {}).get("draft_markdown")) or ""

            report = None
            try:
                from backend.graph.report_builder import build_report_payload

                report = build_report_payload(state=state, query=resolved_query, thread_id=thread_id)
            except Exception as _report_exc:
                _logger.warning(
                    "[chat/supervisor] report build failed: %s",
                    type(_report_exc).__name__,
                )
                report = None

            report_quality, quality_blocked = apply_quality_to_report(report)
            record_quality_metrics(report_quality, source="chat_sync")

            if isinstance(report, dict) and not quality_blocked:
                deps.schedule_report_index(session_id=thread_id, report=report, state=state)

            deps.update_session_context(
                thread_id=thread_id,
                original_query=request.query,
                response_markdown=markdown,
                subject=state.get("subject"),
                skip_context=bool(state.get("skip_session_context")),
            )
            if deps.chat_history_store is not None and markdown:
                deps.chat_history_store.append_turn(
                    session_id=thread_id,
                    user_content=request.query,
                    assistant_content=markdown,
                )

            _elapsed_ms = int((_time.perf_counter() - _t0) * 1000)
            return {
                "success": True,
                "schema_version": deps.chat_response_schema_version,
                "contracts": deps.contract_info(),
                "response": markdown,
                "report": report,
                "quality": report_quality,
                "quality_blocked": quality_blocked,
                "publishable": not quality_blocked,
                "intent": "chat",
                "classification": {"method": "langgraph", "confidence": 1.0},
                "session_id": thread_id,
                "response_time_ms": _elapsed_ms,
                "graph": {
                    "subject": state.get("subject"),
                    "output_mode": state.get("output_mode"),
                    "trace": state.get("trace"),
                },
            }
        except HTTPException:
            raise
        except Exception as exc:
            _logger.error("[chat/supervisor] failed: %s", type(exc).__name__)
            raise HTTPException(status_code=500, detail="Internal server error") from exc

    @router.post("/chat/supervisor/stream")
    async def chat_supervisor_stream_endpoint(
        request: ChatRequest,
        http_request: Request,
        current_user: Principal = Depends(get_current_user),
    ):
        import json as _json

        from backend.services.execution_service import ExecutionDeps, run_graph_pipeline

        require_matching_identity(
            principal=current_user,
            provided=request.session_id,
            expected=current_user.session_id,
            field_name="session_id",
        )
        resolved_session_id = (
            request.session_id if current_user.auth_type == "dev" else current_user.session_id
        )
        try:
            thread_id = deps.resolve_thread_id(resolved_session_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid session_id") from exc

        trace_raw_enabled = deps.resolve_trace_raw_enabled(request)
        ui_context = deps.build_ui_context(request)

        output_mode = None
        strict_selection = None
        confirmation_mode = None
        if getattr(request, "options", None):
            output_mode = request.options.output_mode
            strict_selection = request.options.strict_selection
            confirmation_mode = parse_confirmation_mode(request.options.confirmation_mode)

        # Plan gate (stream variant)
        if str(output_mode or "").strip().lower() == "investment_report":
            principal = getattr(http_request.state, "principal", None)
            enforce_feature(principal, "deep_research")

        # Chat entry point defaults to skip — Chat UI has no InterruptCard.
        # Exception: investment_report mode always requires confirmation (auto).
        if confirmation_mode is None:
            if str(output_mode or "").strip().lower() == "investment_report":
                confirmation_mode = "auto"
            else:
                confirmation_mode = "skip"

        resolved_query = deps.resolve_query_reference(request.query, thread_id)

        exec_deps = ExecutionDeps(
            get_graph_runner=deps.get_graph_runner,
            schedule_report_index=deps.schedule_report_index,
            update_session_context=deps.update_session_context,
            record_chat_turn=(
                deps.chat_history_store.append_turn
                if deps.chat_history_store is not None
                else None
            ),
            redact_sensitive_payload=deps.redact_sensitive_payload,
            is_raw_trace_event=deps.is_raw_trace_event,
            contract_info=deps.contract_info,
            sse_event_schema_version=deps.sse_event_schema_version,
        )

        pipeline = run_graph_pipeline(
            deps=exec_deps,
            query=resolved_query,
            thread_id=thread_id,
            ui_context=ui_context,
            output_mode=output_mode,
            strict_selection=strict_selection,
            confirmation_mode=confirmation_mode,
            original_query=request.query,
            source="chat",
            trace_raw_enabled=trace_raw_enabled,
        )

        def _serialize_sse_item(item: object) -> str:
            def _fallback(value: object):
                if isinstance(value, (datetime, date, dt_time)):
                    return value.isoformat()
                return str(value)

            return _json.dumps(jsonable_encoder(item), ensure_ascii=False, default=_fallback)

        async def _stream():
            async for event in pipeline:
                if isinstance(event, dict) and event.get("type") == "keep-alive":
                    yield f"data: {_serialize_sse_item(event)}\n\n"
                else:
                    yield f"data: {_serialize_sse_item(event)}\n\n"

        return StreamingResponse(
            _stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    @router.get("/api/chat/history")
    async def list_chat_history(
        session_id: str,
        limit: int = 100,
        current_user: Principal = Depends(get_current_user),
    ):
        require_matching_identity(
            principal=current_user,
            provided=session_id,
            expected=current_user.session_id,
            field_name="session_id",
        )
        if deps.chat_history_store is None:
            return {"success": True, "session_id": session_id, "messages": [], "count": 0}
        try:
            thread_id = deps.resolve_thread_id(session_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid session_id") from exc
        messages = deps.chat_history_store.list_messages(session_id=thread_id, limit=limit)
        return {
            "success": True,
            "session_id": thread_id,
            "messages": messages,
            "count": len(messages),
        }

    @router.delete("/api/chat/history")
    async def clear_chat_history(
        session_id: str,
        current_user: Principal = Depends(get_current_user),
    ):
        require_matching_identity(
            principal=current_user,
            provided=session_id,
            expected=current_user.session_id,
            field_name="session_id",
        )
        if deps.chat_history_store is None:
            return {"success": True, "session_id": session_id}
        try:
            thread_id = deps.resolve_thread_id(session_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid session_id") from exc
        deps.chat_history_store.clear(session_id=thread_id)
        deps.get_session_context(thread_id).clear()
        return {"success": True, "session_id": thread_id}

    @router.post("/api/chat/add-chart-data", response_model=ChartDataResponse)
    async def add_chart_data(
        request: dict,
        current_user: Principal = Depends(get_current_user),
    ):
        provided_session_id = request.get("session_id")
        require_matching_identity(
            principal=current_user,
            provided=provided_session_id,
            expected=current_user.session_id,
            field_name="session_id",
        )
        resolved_session_id = (
            provided_session_id if current_user.auth_type == "dev" else current_user.session_id
        )
        ticker = request.get("ticker")
        summary = request.get("summary", "")
        if not ticker or not summary:
            raise HTTPException(status_code=400, detail="Missing ticker or summary")
        if not isinstance(ticker, str) or len(ticker) > _MAX_CHART_TICKER_CHARS:
            raise HTTPException(status_code=400, detail="Invalid ticker")
        if not isinstance(summary, str) or len(summary) > _MAX_CHART_SUMMARY_CHARS:
            raise HTTPException(status_code=400, detail="Invalid summary")

        try:
            try:
                session_id = deps.resolve_thread_id(resolved_session_id)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail="Invalid session_id") from exc

            chart_message = f"[Chart Data] {summary}"
            deps.get_session_context(session_id).add_turn(
                query=f"View chart data for {ticker}",
                intent="chat",
                response=chart_message,
                metadata={"ticker": ticker, "tickers": [ticker], "chart_data": True},
            )

            return {"success": True, "message": "Chart data added to context", "session_id": session_id}
        except HTTPException:
            raise
        except Exception as exc:
            _logger.error("[chat/add-chart-data] failed: %s", type(exc).__name__)
            raise HTTPException(status_code=500, detail="Internal server error") from exc

    return router
