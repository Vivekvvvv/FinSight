"""Shared helpers for the graph execution service."""

from __future__ import annotations

import math
import os
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from backend.report.quality_engine import apply_quality_to_report, record_quality_metrics


def _utc_iso_now() -> str:
    return datetime.now(UTC).isoformat()

def _normalize_run_id(run_id: str | None) -> str:
    value = str(run_id or "").strip()
    return value or str(uuid4())

def _normalize_report_source_type(source: str | None) -> str:
    raw = str(source or "").strip().lower()
    if not raw:
        return "ai_generated"
    if raw.startswith("dashboard"):
        return "dashboard"
    if raw.startswith("chat"):
        return "chat"
    if raw.startswith("workbench"):
        return "workbench"
    return raw[:64]

def _resolve_ticker_override(ui_context: dict[str, Any] | None) -> str | None:
    if not isinstance(ui_context, dict):
        return None
    tickers = ui_context.get("tickers_override")
    if not isinstance(tickers, list):
        return None
    for item in tickers:
        value = str(item or "").strip().upper()
        if value:
            return value
    return None

def _annotate_report_source(
    report: dict[str, Any] | None,
    source: str | None,
    ticker_override: str | None = None,
) -> dict[str, Any] | None:
    if not isinstance(report, dict):
        return report

    source_type = _normalize_report_source_type(source)
    report["source_type"] = source_type

    normalized_ticker = str(ticker_override or "").strip().upper()
    if normalized_ticker:
        report["ticker"] = normalized_ticker

    meta = report.get("meta")
    if not isinstance(meta, dict):
        meta = {}
    meta["source_type"] = source_type
    if source:
        meta["source_trigger"] = str(source).strip()
    report["meta"] = meta
    return report

def _apply_quality_gate(
    *,
    report: dict[str, Any] | None,
    source: str,
) -> tuple[dict[str, Any], bool]:
    quality, blocked = apply_quality_to_report(report)
    record_quality_metrics(quality, source=source)
    return quality, blocked

def _execution_timeout_seconds(output_mode: str | None = None) -> float:
    """
    Resolve execution timeout with mode-aware defaults.

    - brief/chat/default: LANGGRAPH_EXECUTION_TIMEOUT_SECONDS (default 500s)
    - investment_report: LANGGRAPH_EXECUTION_TIMEOUT_REPORT_SECONDS (default 900s)
      fallback to LANGGRAPH_EXECUTION_TIMEOUT_SECONDS when report-specific key is absent.
    """
    mode = (output_mode or "").strip().lower()
    default_base = "500"
    default_report = "900"
    raw = (
        os.getenv("LANGGRAPH_EXECUTION_TIMEOUT_REPORT_SECONDS", default_report)
        if mode == "investment_report"
        else os.getenv("LANGGRAPH_EXECUTION_TIMEOUT_SECONDS", default_base)
    )
    try:
        parsed = float(raw)
        if not math.isfinite(parsed):
            raise ValueError("execution timeout must be finite")
        return max(60.0, parsed)
    except Exception:
        return 900.0 if mode == "investment_report" else 500.0
