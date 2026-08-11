"""LLM JSON parsing and repair helpers extracted from planner.py."""
from __future__ import annotations

import json
import re
from typing import Any

from backend.utils.strict_json import json_loads_strict

def _extract_json_object(text: str) -> str:
    """
    Extract the first JSON object from a model response.
    Handles code fences and surrounding commentary.
    """
    if not text:
        raise ValueError("empty model output")

    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no json object found")
    return cleaned[start : end + 1]


def _extract_error_snippet(text: str, pos: int, *, radius: int = 220) -> str:
    raw = str(text or "")
    idx = max(0, min(len(raw), int(pos or 0)))
    start = max(0, idx - radius)
    end = min(len(raw), idx + radius)
    return raw[start:end].strip()


def _build_parse_error_info(raw_output: str, exc: BaseException) -> dict[str, Any]:
    payload: dict[str, Any] = {"error": type(exc).__name__}
    raw = str(raw_output or "")

    try:
        json_candidate = _extract_json_object(raw)
    except Exception:
        json_candidate = raw

    payload["output_preview"] = json_candidate[:1200]
    if isinstance(exc, json.JSONDecodeError):
        payload["line"] = int(exc.lineno)
        payload["column"] = int(exc.colno)
        payload["pos"] = int(exc.pos)
        payload["snippet"] = _extract_error_snippet(json_candidate, exc.pos)
    else:
        payload["snippet"] = json_candidate[:320]
    return payload


def _public_parse_error_info(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    public: dict[str, Any] = {}
    for key in ("json_retry_used", "line", "column", "pos"):
        if key in value:
            public[key] = value[key]
    if "error" in value:
        public["error"] = "invalid_json"
    for key in ("first_attempt", "second_attempt"):
        if isinstance(value.get(key), dict):
            public[key] = _public_parse_error_info(value[key])
    return public


def _repair_json_text(text: str) -> str:
    repaired = str(text or "")
    if not repaired:
        return repaired

    repaired = repaired.replace("\ufeff", "")
    repaired = repaired.translate(
        str.maketrans(
            {
                "“": '"',
                "”": '"',
                "‘": "'",
                "’": "'",
                "，": ",",
                "：": ":",
            }
        )
    )
    repaired = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", repaired)
    repaired = re.sub(r",(\s*[}\]])", r"\1", repaired)
    repaired = re.sub(r"([{,]\s*)'([^'\\]+?)'(\s*:)", r'\1"\2"\3', repaired)
    repaired = re.sub(r"([{,]\s*)([A-Za-z_][A-Za-z0-9_\-]*)(\s*:)", r'\1"\2"\3', repaired)

    def _replace_single_quoted_value(match: re.Match[str]) -> str:
        body = match.group(1).replace('\\"', '"').replace("\\'", "'")
        escaped = json.dumps(body, ensure_ascii=False)
        return f": {escaped}{match.group(2)}"

    repaired = re.sub(r":\s*'([^'\\]*(?:\\.[^'\\]*)*)'(\s*[,}])", _replace_single_quoted_value, repaired)
    return repaired


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def _load_json_with_repair(json_text: str) -> tuple[Any, dict[str, Any]]:
    raw = str(json_text or "")
    attempts: list[tuple[str, str]] = [("raw", raw)]

    sanitized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", raw)
    if sanitized != raw:
        attempts.append(("control_char_sanitized", sanitized))

    repaired = _repair_json_text(sanitized)
    if repaired != sanitized:
        attempts.append(("syntax_repaired", repaired))

    last_exc: BaseException | None = None
    for mode, candidate in attempts:
        try:
            return json_loads_strict(candidate, strict=False), {"parse_mode": mode}
        except Exception as exc:  # noqa: PERF203
            last_exc = exc

    if last_exc is not None:
        raise last_exc
    raise ValueError("json_parse_failed")


def _build_json_retry_prompt(
    *,
    base_prompt: str,
    parse_error: dict[str, Any],
    invalid_output: str,
) -> str:
    line = parse_error.get("line")
    col = parse_error.get("column")
    position = f"line={line}, col={col}" if line and col else "unknown"
    snippet = str(parse_error.get("snippet") or "")[:800]
    preview = str(invalid_output or "")[:3200]
    return (
        f"{base_prompt}\n\n"
        "[FORMAT_RECOVERY]\n"
        "Your previous output was not valid JSON.\n"
        f"- Parse error: {parse_error.get('error')}\n"
        f"- Parse position: {position}\n"
        f"- Error snippet: {snippet}\n\n"
        "Return ONLY a valid JSON object. Do not include markdown/code fences/explanations.\n"
        "Rules:\n"
        "1) Use double quotes for every key and string value.\n"
        "2) No trailing commas.\n"
        "3) Output must be parseable by Python json.loads.\n\n"
        "[PREVIOUS_INVALID_OUTPUT]\n"
        f"{preview}\n"
    )
