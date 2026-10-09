# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import logging
import math
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from backend.report.quality_engine import evaluate_runtime_report_quality
from backend.report.validator import ReportValidator
from backend.utils.strict_json import json_loads_strict

logger = logging.getLogger(__name__)

from backend.graph.report_text_tools import (
    _env_int,
    _now_iso,
    _safe_str,
    _to_json_compatible,
    _sanitize_deep_search_summary,
    _flatten_json_like_line,
    _sanitize_report_text_block,
    _harden_report_payload,
    _parse_iso_datetime,
    _freshness_hours,
    _count_content_chars,
    _to_bullets,
    _normalize_line_for_dedupe,
    _dedupe_markdown_lines,
    _extract_deep_research_points,
)

from backend.graph.report_grounding import (
    _GROUNDING_CLAIM_PATTERNS,
    _normalize_for_grounding,
    _extract_grounding_claims,
    _build_grounding_corpus,
    _is_claim_grounded,
    _compute_grounding_stats,
)

from backend.graph.report_citations import (
    _build_citations,
    _build_filing_section_citations,
    _build_internal_citation_key,
    _build_internal_citation_url,
    _canonicalize_url_for_citation_match,
    _safe_confidence,
)

from backend.graph.report_agent_steps import (
    _AGENT_TITLE_MAP,
    _agent_status_from_steps,
    _agent_summaries_from_steps,
)

from backend.graph.report_core_viewpoints import (
    _build_core_viewpoints,
    _extract_headline,
)

from backend.graph.report_hints import (
    _build_report_quality_hints,
    _classify_report_type,
    _derive_report_tags_and_hints,
    _infer_market_from_context,
    _is_deep_report_query,
)



from backend.graph.report_payload import (
    _agent_report_input_snapshot,
    _build_long_synthesis_report,
    _build_report_payload_impl,
    _extract_risks,
    _extend_synthesis_report_if_short,
    build_report_payload,
)
