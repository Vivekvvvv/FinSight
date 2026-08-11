# -*- coding: utf-8 -*-
"""Hallucination guards and evidence-claim helpers.

Extracted from graph.nodes.synthesize; synthesize re-exports every name
here for backward compatibility.
"""
from __future__ import annotations

import logging
import re
from typing import Any


logger = logging.getLogger(__name__)


#   A) 「预计/计划」前缀 + 未来年份 + 事件动词
#   B) 事件动词 + 括号内月份/季度（直陈式，最危险）
#      例：「Gemini 1.5模型发布（2月底）」「新品推出（2026Q1）」
#   C) 括号内年份/季度 + 事件动词（倒装格式）
_FUTURE_EVENT_VERBS = r"(?:发布|推出|上线|发售|量产|落地|开售|开源|并购|收购|拆分|披露|宣布|实施|完成)"
# 时间短语：「2月底」「3月中旬」「Q1」「2026Q2」「下半年」等
_FUTURE_DATE_PHRASE = (
    r"(?:"
    r"\d{1,2}月[初中底前后旬]?"
    r"|[上下]半年|年[初中底]"
    r"|Q[1-4]\s*\d{0,4}"
    r"|\d{4}\s*年\s*\d{1,2}月"
    r"|\d{4}\s*Q[1-4]"
    r")"
)
_HALLUCINATION_EVENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    # A-1: 前缀式 — 「预计/计划/拟于/即将/有望」+ 年份 + 动词
    re.compile(
        r"(?:预计|计划|拟于|即将|有望(?:于)?)\s*20\d{2}\s*(?:年|Q[1-4])"
        r"[^\n。；;]{0,26}" + _FUTURE_EVENT_VERBS +
        r"[^\n。；;]{0,28}",
        flags=re.IGNORECASE,
    ),
    # A-2: 前缀式 — 动词先出，年份后出
    re.compile(
        r"(?:预计|计划|拟于|即将|有望(?:于)?)[^\n。；;]{0,20}" + _FUTURE_EVENT_VERBS +
        r"[^\n。；;]{0,20}(?:20\d{2}\s*(?:年|Q[1-4]))"
        r"[^\n。；;]{0,16}",
        flags=re.IGNORECASE,
    ),
    # B: 直陈式 — 事件名 + 括号时间（最危险，模型直接当事实输出）
    # 例：「Gemini 1.5模型发布（2月底）」「Adani数据合作（2026Q1）」
    re.compile(
        r"[^\n。；;]{0,35}" + _FUTURE_EVENT_VERBS +
        r"\s*[（(]\s*" + _FUTURE_DATE_PHRASE + r"\s*[）)]",
        flags=re.IGNORECASE,
    ),
    # C: 倒装式 — 括号时间在前，动词在后
    re.compile(
        r"[（(]\s*" + _FUTURE_DATE_PHRASE + r"\s*[）)]"
        r"[^\n。；;]{0,40}" + _FUTURE_EVENT_VERBS,
        flags=re.IGNORECASE,
    ),
)
_HALLUCINATION_SAFE_PLACEHOLDER = "[此处信息未经证据验证，已移除]"



def _normalize_for_match(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()



def _claim_supported_by_evidence(claim: str, evidence_text: str) -> bool:
    normalized_claim = _normalize_for_match(claim)
    normalized_evidence = _normalize_for_match(evidence_text)
    if not normalized_claim or not normalized_evidence:
        return False

    if normalized_claim in normalized_evidence:
        return True

    year_match = re.search(r"20\d{2}(?:年|q[1-4])?", claim, flags=re.IGNORECASE)
    # 同时检测模糊月份短语，如「2月底」「3月中旬」「Q1」
    month_match = re.search(
        r"(?:\d{1,2}月[初中底前后旬]?|[上下]半年|年[初中底]|Q[1-4])",
        claim, flags=re.IGNORECASE
    )
    date_match = year_match or month_match
    verb_match = re.search(
        r"(发布|推出|上线|发售|量产|落地|开售|开源|并购|收购|拆分|披露|宣布|实施|完成)",
        claim
    )
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9._-]{2,}|[\u4e00-\u9fff]{2,}", claim)
    stopwords = {"预计", "计划", "拟于", "即将", "有望", "发布", "推出", "上线", "发售", "量产", "落地",
                 "开售", "开源", "并购", "收购", "拆分", "披露", "宣布", "实施", "完成"}

    key_tokens: list[str] = []
    if year_match:
        key_tokens.append(year_match.group(0))
    elif month_match:
        # 模糊月份权重与年份等同：必须在证据中明确出现才算支撑
        key_tokens.append(month_match.group(0))
    if verb_match:
        key_tokens.append(verb_match.group(0))
    for token in tokens:
        token_norm = token.lower()
        if token in stopwords or token_norm in stopwords:
            continue
        key_tokens.append(token)

    hits = 0
    for token in key_tokens[:8]:
        if _normalize_for_match(token) in normalized_evidence:
            hits += 1

    # 有明确时间锚（年份或月份）时，要求同时命中实体 token → 阈值 2
    # 无时间锚时，要求 3 个 token 全命中（更严格）
    if date_match:
        return hits >= 2
    return hits >= 3



def _scrub_unverified_future_claims(text: str, evidence_text: str) -> str:
    if not isinstance(text, str) or not text.strip():
        return ""

    cleaned = text
    for pattern in _HALLUCINATION_EVENT_PATTERNS:
        def _replace(match: re.Match[str]) -> str:
            claim = match.group(0)
            if _claim_supported_by_evidence(claim, evidence_text):
                return claim
            logger.warning("[Synthesize] scrubbed unverified future claim")
            return _HALLUCINATION_SAFE_PLACEHOLDER

        cleaned = pattern.sub(_replace, cleaned)

    cleaned = re.sub(
        rf"(?:{re.escape(_HALLUCINATION_SAFE_PLACEHOLDER)}\s*){{2,}}",
        _HALLUCINATION_SAFE_PLACEHOLDER + " ",
        cleaned,
    ).strip()
    return cleaned



def _normalize_verifier_claims(raw_claims: Any, *, max_items: int) -> list[dict[str, str]]:
    if not isinstance(raw_claims, list):
        return []

    claims: list[dict[str, str]] = []
    for item in raw_claims:
        if len(claims) >= max_items:
            break
        if not isinstance(item, dict):
            continue
        claim = str(item.get("claim") or "").strip()
        reason = str(item.get("reason") or "").strip()
        if not claim:
            continue
        claims.append(
            {
                "claim": claim[:240],
                "reason": reason[:240] if reason else "证据池中未找到明确支撑",
            }
        )
    return claims



def _apply_verifier_redactions(text: str, claims: list[dict[str, str]]) -> str:
    cleaned = str(text or "")
    if not cleaned.strip() or not claims:
        return cleaned

    for item in claims:
        claim = str(item.get("claim") or "").strip()
        if not claim:
            continue
        if claim in cleaned:
            cleaned = cleaned.replace(claim, _HALLUCINATION_SAFE_PLACEHOLDER)

    cleaned = re.sub(
        rf"(?:{re.escape(_HALLUCINATION_SAFE_PLACEHOLDER)}\s*){{2,}}",
        _HALLUCINATION_SAFE_PLACEHOLDER + " ",
        cleaned,
    ).strip()
    return cleaned



def _contains_claim_after_redaction(text: str, claim: str) -> bool:
    cleaned_text = str(text or "").strip()
    cleaned_claim = str(claim or "").strip()
    if not cleaned_text or not cleaned_claim:
        return False

    if cleaned_claim in cleaned_text:
        return True

    normalized_text = _normalize_for_match(cleaned_text)
    normalized_claim = _normalize_for_match(cleaned_claim)
    if not normalized_text or not normalized_claim:
        return False
    return normalized_claim in normalized_text



def _compute_unresolved_unsupported_claims(
    text: str,
    claims: list[dict[str, str]] | None,
) -> list[dict[str, str]]:
    if not claims:
        return []

    unresolved: list[dict[str, str]] = []
    for item in claims:
        if not isinstance(item, dict):
            continue
        claim = str(item.get("claim") or "").strip()
        if not claim:
            continue
        if _contains_claim_after_redaction(text, claim):
            unresolved.append(
                {
                    "claim": claim[:240],
                    "reason": str(item.get("reason") or "").strip()[:240],
                }
            )
    return unresolved

