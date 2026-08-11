"""Module-level helpers for DeepSearchAgent text/JSON handling."""

import json
import re
from typing import Any, Dict

from backend.utils.strict_json import json_loads_strict


def _extract_json(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        return {}
    try:
        return json_loads_strict(match.group(0))
    except (json.JSONDecodeError, ValueError):
        return {}


def _clean_degraded_text(text: str) -> str:
    cleaned = str(text or "")
    cleaned = re.sub(r"https?://\S+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    noise_tokens = (
        "SummaryRatingsFinancialsTechnicals",
        "MarketWatch",
        "Privacy Policy",
        "Terms of Use",
        "Cookie",
        "Subscribe",
        "Sign in",
        "Login",
        "??",
        "??",
        "????",
    )
    for token in noise_tokens:
        cleaned = cleaned.replace(token, " ")
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned


def _low_signal_text(text: str) -> bool:
    if not text:
        return True
    stripped = text.strip()
    if len(stripped) < 20:
        return True
    alpha_num = len(re.findall(r"[A-Za-z0-9\u4e00-\u9fff]", stripped))
    if alpha_num < 15:
        return True
    if re.search(r"[A-Za-z]{25,}", stripped):
        return True
    return False


def _degraded_fact_from_doc(doc: Dict[str, Any]) -> str:
    title = _clean_degraded_text(str(doc.get("title") or "")).strip()
    snippet = _clean_degraded_text(str(doc.get("snippet") or doc.get("content") or "")).strip()
    if not snippet:
        snippet = _clean_degraded_text(str(doc.get("content") or "")).strip()
    if _low_signal_text(snippet):
        return ""

    if len(snippet) > 140:
        snippet = snippet[:140].rstrip(" ,.;???") + "?"

    idx_ref = doc.get("_idx_ref")
    ref = f"[{idx_ref}]" if idx_ref else ""
    if title:
        return f"- {title}?{snippet} {ref}".strip()
    return f"- {snippet} {ref}".strip()
