# -*- coding: utf-8 -*-
"""Deterministic agent viewpoint extraction (zero LLM) extracted from report_builder.py."""
from __future__ import annotations

import re as _re
from typing import Any

from backend.graph.report_text_tools import (
    _safe_str,
)
from backend.graph.report_citations import (
    _safe_confidence,
)

_HEADLINE_SPLIT_RE = _re.compile(r"(?<=[。；\n])|(?<=\.)(?=\s|$)")
_HEADLINE_MAX_LEN = 120

def _extract_headline(summary: str) -> str:
    """Extract the first meaningful sentence from agent summary text.

    Split on Chinese period (。), semicolon (；), newline, or English period
    followed by whitespace/end-of-string (avoids splitting on decimals like 5.3%).
    If the first sentence exceeds _HEADLINE_MAX_LEN chars, truncate with '…'.
    """
    if not summary or not summary.strip():
        return "（无摘要）"

    text = summary.strip()
    # Remove leading markdown bullets / numbering (e.g. "- ", "* ", "## ", "1. ")
    text = _re.sub(r"^[\s\-\*#]*(?:\d+\.\s)?", "", text).strip()
    if not text:
        return "（无摘要）"

    parts = _HEADLINE_SPLIT_RE.split(text, maxsplit=1)
    headline = (parts[0] or "").strip()
    if not headline:
        headline = text[:_HEADLINE_MAX_LEN]

    if len(headline) > _HEADLINE_MAX_LEN:
        headline = headline[:_HEADLINE_MAX_LEN] + "…"

    return headline

def _build_core_viewpoints(
    agent_summaries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build structured per-agent viewpoint list from agent_summaries.

    Pure deterministic extraction — zero LLM, zero external calls.
    Only includes agents with status == "success".
    Returns empty list when no successful agents exist (frontend falls back
    to report.summary markdown blob).
    """
    viewpoints: list[dict[str, Any]] = []

    for ag in agent_summaries:
        if not isinstance(ag, dict):
            continue
        if ag.get("status") != "success":
            continue

        summary_text = _safe_str(ag.get("summary") or "")
        headline = _extract_headline(summary_text)

        evidence_full = ag.get("evidence_full")
        evidence_count = len(evidence_full) if isinstance(evidence_full, list) else 0

        data_sources = ag.get("data_sources")
        if not isinstance(data_sources, list):
            data_sources = []

        confidence = max(0.0, min(1.0, _safe_confidence(ag.get("confidence"), default=0.0)))

        viewpoints.append({
            "agent_name": ag.get("agent_name", ""),
            "title": ag.get("title", ag.get("agent_name", "")),
            "headline": headline,
            "detail": summary_text,
            "confidence": confidence,
            "data_sources": [str(s) for s in data_sources if str(s).strip()][:8],
            "evidence_count": evidence_count,
            "status": "success",
        })

    # Preserve original agent ordering
    viewpoints.sort(key=lambda v: next(
        (i for i, a in enumerate(agent_summaries)
         if isinstance(a, dict) and a.get("agent_name") == v["agent_name"]),
        999,
    ))

    return viewpoints
