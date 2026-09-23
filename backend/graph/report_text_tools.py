# -*- coding: utf-8 -*-
"""Report text / payload hardening helpers.

Extracted from graph.report_builder to keep the builder module focused;
report_builder re-exports every name here for backward compatibility.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
from datetime import datetime, timezone
from typing import Any

from backend.utils.strict_json import json_loads_strict


logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(str(raw).strip())
    except Exception:
        return default



def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()



def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return str(value)



def _token_in_text(token: str, text: str) -> bool:
    """token 子串匹配：≤3 字符的 ASCII token 需字母数字边界，
    否则 "rsi"⊂"university"/"diversification" 这类幻影命中。"""
    if len(token) <= 3 and token.isascii():
        pattern = r"(?<![a-zA-Z0-9])" + re.escape(token) + r"(?![a-zA-Z0-9])"
        return re.search(pattern, text) is not None
    return token in text



def _to_json_compatible(value: Any) -> Any:
    try:
        return json.loads(
            json.dumps(value, ensure_ascii=False, default=str, allow_nan=False)
        )
    except Exception:
        if isinstance(value, float) and not math.isfinite(value):
            return None
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, list):
            return [_to_json_compatible(item) for item in value]
        if isinstance(value, dict):
            return {str(k): _to_json_compatible(v) for k, v in value.items()}
        return _safe_str(value)



def _sanitize_deep_search_summary(summary: str, agent_name: str) -> str:
    if agent_name != "deep_search_agent":
        return summary
    text = _safe_str(summary)
    if not text.strip():
        return text

    noise_markers = (
        "SummaryRatingsFinancialsTechnicals",
        "MarketWatch",
        "Privacy Policy",
        "Terms of Use",
    )
    noisy = any(marker in text for marker in noise_markers)
    if not noisy:
        loop_heading = re.compile(r"^\s*深度补充说明（第\d+轮）\s*$", flags=re.M)
        if loop_heading.search(text):
            seen_loop_bodies: set[str] = set()
            out_lines: list[str] = []
            lines = text.splitlines()
            i = 0
            while i < len(lines):
                line = _safe_str(lines[i]).strip()
                if not line:
                    out_lines.append("")
                    i += 1
                    continue
                if loop_heading.match(line):
                    i += 1
                    body: list[str] = []
                    while i < len(lines):
                        nxt = _safe_str(lines[i]).strip()
                        if loop_heading.match(nxt):
                            break
                        body.append(_safe_str(lines[i]))
                        i += 1
                    body_text = "\n".join(body).strip()
                    body_key = re.sub(r"\s+", " ", body_text)
                    if body_key and body_key not in seen_loop_bodies:
                        seen_loop_bodies.add(body_key)
                        out_lines.append("## 深度补充说明")
                        out_lines.extend(body)
                    continue
                out_lines.append(_safe_str(lines[i]))
                i += 1
            return "\n".join(out_lines).strip()

        return text

    cleaned = re.sub(r"https?://\S+", "", text)
    for marker in noise_markers:
        cleaned = cleaned.replace(marker, " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) > 500:
        cleaned = cleaned[:500].rstrip(" ,.;，。；") + "…"

    return (
        f"深度研究摘要（质量保护模式）：{cleaned}\n\n"
        "注意：建议结合财报、公告或权威媒体原文复核关键结论。"
    )



def _flatten_json_like_line(line: str) -> str:
    text = _safe_str(line).strip()
    if not text:
        return ""

    was_bullet = text.startswith("- ")
    candidate = text[2:].strip() if was_bullet else text
    if not (candidate.startswith("{") and candidate.endswith("}")):
        return text

    try:
        obj = json_loads_strict(candidate)
    except Exception:
        return text
    if not isinstance(obj, dict):
        return text

    event = _safe_str(obj.get("event")).strip()
    impact = _safe_str(obj.get("impact")).strip()
    if event and impact:
        merged = f"{event}：{impact}"
        return f"- {merged}" if was_bullet else merged

    risk = _safe_str(obj.get("risk")).strip()
    detail = _safe_str(obj.get("detail")).strip()
    if risk and detail:
        merged = f"{risk}：{detail}"
        return f"- {merged}" if was_bullet else merged

    title = _safe_str(obj.get("title") or obj.get("name")).strip()
    summary = _safe_str(obj.get("summary") or obj.get("reason") or obj.get("value")).strip()
    if title and summary:
        merged = f"{title}：{summary}"
        return f"- {merged}" if was_bullet else merged

    pairs: list[str] = []
    for key, value in obj.items():
        key_text = _safe_str(key).strip()
        value_text = _safe_str(value).strip()
        if not key_text or not value_text:
            continue
        pairs.append(f"{key_text}: {value_text}")
        if len(pairs) >= 3:
            break
    if not pairs:
        return text
    merged = "；".join(pairs)
    return f"- {merged}" if was_bullet else merged



def _sanitize_report_text_block(text: str, *, max_lines: int = 24, max_chars: int = 4000) -> str:
    raw = _safe_str(text)
    if not raw.strip():
        return ""

    out_lines: list[str] = []
    for line in raw.splitlines():
        normalized = _flatten_json_like_line(line)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        if not normalized:
            continue
        if any(marker in normalized for marker in ("<inputs>", "</inputs>", "```", "待实现", "TBD", "TODO")):
            continue
        out_lines.append(normalized)
        if len(out_lines) >= max_lines:
            break

    if not out_lines:
        return ""

    normalized_text = "\n".join(out_lines)
    if len(normalized_text) > max_chars:
        normalized_text = normalized_text[:max_chars].rstrip(" ,.;，。；") + "…"
    return normalized_text



def _harden_report_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return payload

    sections = payload.get("sections")
    if not isinstance(sections, list):
        sections = []

    repaired_sections: list[dict[str, Any]] = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        contents = section.get("contents")
        if not isinstance(contents, list):
            contents = []

        repaired_contents: list[dict[str, Any]] = []
        for content in contents:
            if not isinstance(content, dict):
                continue
            content_type = _safe_str(content.get("type") or "text").strip() or "text"
            text = _safe_str(content.get("content") or "")
            if content_type == "text" and text:
                if re.search(r"^\s*-?\s*\{[^\n]*\}\s*$", text, flags=re.M):
                    text = _sanitize_report_text_block(text, max_lines=20, max_chars=2200) or text
            if content_type == "text" and not text.strip():
                text = "（该部分暂无结构化内容）"

            repaired_contents.append(
                {
                    "type": content_type,
                    "content": text,
                    "citation_refs": content.get("citation_refs") if isinstance(content.get("citation_refs"), list) else [],
                    "metadata": content.get("metadata") if isinstance(content.get("metadata"), dict) else {},
                }
            )

        if not repaired_contents:
            repaired_contents = [{"type": "text", "content": "（该部分暂无结构化内容）", "citation_refs": [], "metadata": {}}]

        repaired = dict(section)
        repaired["contents"] = repaired_contents
        repaired_sections.append(repaired)

    payload["sections"] = repaired_sections

    summary = _safe_str(payload.get("summary") or "")
    if re.search(r"^\s*\{[^\n]*\}\s*$", summary):
        summary = _sanitize_report_text_block(summary, max_lines=2, max_chars=420)
    if not summary.strip():
        for section in repaired_sections:
            for content in section.get("contents") or []:
                if not isinstance(content, dict):
                    continue
                if _safe_str(content.get("type") or "") != "text":
                    continue
                candidate = _safe_str(content.get("content") or "").strip()
                if candidate:
                    summary = candidate[:400]
                    break
            if summary:
                break
    payload["summary"] = summary or "（暂无摘要）"

    synthesis_report = _safe_str(payload.get("synthesis_report") or "")
    if not synthesis_report.strip():
        lines = ["## 投资摘要", f"- {payload['summary']}"]
        for section in repaired_sections[:6]:
            section_title = _safe_str(section.get("title") or "")
            if not section_title:
                continue
            lines.append(f"## {section_title}")
            first_text = ""
            for content in section.get("contents") or []:
                if isinstance(content, dict) and _safe_str(content.get("type") or "") == "text":
                    first_text = _safe_str(content.get("content") or "").strip()
                    if first_text:
                        break
            lines.append(f"- {first_text[:240] or '（暂无内容）'}")
        synthesis_report = "\n".join(lines)
    elif re.search(r"^\s*-?\s*\{[^\n]*\}\s*$", synthesis_report, flags=re.M):
        synthesis_report = _sanitize_report_text_block(synthesis_report, max_lines=120, max_chars=12000) or synthesis_report
    payload["synthesis_report"] = synthesis_report

    risks = payload.get("risks")
    if isinstance(risks, list):
        cleaned_risks = [_safe_str(item).strip() for item in risks if _safe_str(item).strip()]
        payload["risks"] = cleaned_risks or ["报告已自动降级生成，建议结合原始数据复核。"]
    else:
        payload["risks"] = ["报告已自动降级生成，建议结合原始数据复核。"]

    return payload



def _parse_iso_datetime(value: str) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    # Accept a few common formats.
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    except Exception:
        return None



def _freshness_hours(published_date: str | None) -> float:
    if not published_date:
        return 24.0
    dt = _parse_iso_datetime(str(published_date))
    if not dt:
        return 24.0
    # naive 串按 UTC 基准取 now（多数新闻源给无 Z 的 UTC 时间）；裸 datetime.now()
    # 是本地墙钟，东八区会把 freshness 系统性放大 8 小时
    now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now(timezone.utc).replace(tzinfo=None)
    delta = now - dt
    return max(0.0, delta.total_seconds() / 3600.0)



def _count_content_chars(markdown: str) -> int:
    """
    Roughly align with frontend `countContentChars()`:
    Chinese chars + English words/numbers, after stripping common markdown syntax.
    """
    if not markdown:
        return 0
    text = str(markdown)
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`]*`", "", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    # links → keep link text
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"(\*{1,3}|_{1,3})(.*?)\1", r"\2", text)
    text = re.sub(r"~~.*?~~", "", text)
    text = re.sub(r"^[\s]*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[\s]*\d+\.\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^>+\s?", "", text, flags=re.MULTILINE)
    text = re.sub(r"---+|===+|\*\*\*+", "", text)
    text = text.replace("|", " ")
    # Ignore raw URLs (they should not count towards "content length").
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[:\-]+", " ", text)
    chinese = len(re.findall(r"[\u4e00-\u9fff\u3400-\u4dbf]", text))
    words = len(re.findall(r"[a-zA-Z0-9]+", text))
    return chinese + words



def _to_bullets(text: str, *, limit: int = 8) -> list[str]:
    if not isinstance(text, str) or not text.strip():
        return []
    lines: list[str] = []
    for raw in text.splitlines():
        line = _safe_str(raw).strip()
        if not line:
            continue
        line = line.lstrip("-").strip()
        if not line:
            continue
        lines.append(line[:220])
        if len(lines) >= limit:
            break
    return lines



def _normalize_line_for_dedupe(line: str) -> str:
    normalized = _safe_str(line)
    normalized = re.sub(r"\[[0-9]+\]", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip().lower()
    normalized = normalized.lstrip("- ")
    return normalized



def _dedupe_markdown_lines(text: str, *, keep_heading_repeats: bool = False) -> str:
    if not isinstance(text, str) or not text.strip():
        return ""

    seen: set[str] = set()
    output: list[str] = []
    for raw in text.splitlines():
        line = _safe_str(raw)
        stripped = line.strip()
        if not stripped:
            if output and output[-1] == "":
                continue
            output.append("")
            continue

        if stripped.startswith("##") and keep_heading_repeats:
            output.append(stripped)
            continue

        key = _normalize_line_for_dedupe(stripped)
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        output.append(stripped)

    return "\n".join(output).strip()



def _extract_deep_research_points(summary: str, *, limit: int = 6) -> list[str]:
    text = _safe_str(summary).strip()
    if not text:
        return []

    cleaned = _sanitize_deep_search_summary(text, "deep_search_agent")
    points: list[str] = []
    for raw in cleaned.splitlines():
        line = _safe_str(raw).strip()
        if not line:
            continue
        if line.startswith("##"):
            continue
        line = line.lstrip("- ").strip()
        if not line:
            continue
        if len(line) > 220:
            line = line[:220].rstrip(" ,.;，。；") + "..."
        points.append(line)
        if len(points) >= limit:
            break
    return points

