# -*- coding: utf-8 -*-
"""Report tags/classification/quality-hints derivation extracted from report_builder.py."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from backend.graph.report_text_tools import (
    _safe_str,
    _token_in_text,
)


def _derive_report_tags_and_hints(
    *,
    subject_type: str,
    tickers: list[str],
    render_vars: dict[str, Any],
    agent_status: dict[str, Any],
) -> tuple[list[str], dict[str, Any]]:
    compare_basis: list[str] = []
    if len(tickers) > 1:
        compare_basis.append("multi_ticker")

    comparison_conclusion = _safe_str(render_vars.get("comparison_conclusion") or "").strip()
    if comparison_conclusion:
        compare_basis.append("comparison_conclusion")

    comparison_metrics = render_vars.get("comparison_metrics")
    if isinstance(comparison_metrics, str) and comparison_metrics.strip():
        compare_basis.append("comparison_metrics")

    is_compare = len(compare_basis) > 0

    conflict_agents: list[str] = []
    for agent_name, payload in agent_status.items():
        if not isinstance(agent_name, str) or not isinstance(payload, dict):
            continue
        evidence_quality = payload.get("evidence_quality")
        has_conflicts = (
            isinstance(evidence_quality, dict)
            and evidence_quality.get("has_conflicts") is True
        )
        if has_conflicts:
            conflict_agents.append(agent_name)

    conflict_agents = sorted(set(conflict_agents))
    has_conflict = len(conflict_agents) > 0

    tags: list[str] = []
    if is_compare:
        tags.append("compare")
    if has_conflict:
        tags.append("conflict")
    if subject_type in ("filing", "research_doc"):
        tags.append("filing")

    hints: dict[str, Any] = {
        "is_compare": is_compare,
        "has_conflict": has_conflict,
        "compare_basis": compare_basis,
        "conflict_agents": conflict_agents,
    }
    return tags, hints

def _is_deep_report_query(query: str) -> bool:
    return _classify_report_type(query) == "deep_financial"

_QUALITY_PROFILES: dict[str, dict[str, bool]] = {
    "deep_financial": {
        "10k": True,
        "10q": True,
        "local_filing": False,
        "transcript": True,
        "media": True,
        "snippets": True,
    },
    "general": {
        "10k": False,
        "10q": False,
        "local_filing": False,
        "transcript": False,
        "media": True,
        "snippets": True,
    },
    "technical": {
        "10k": False,
        "10q": False,
        "local_filing": False,
        "transcript": False,
        "media": False,
        "snippets": True,
    },
    "news": {
        "10k": False,
        "10q": False,
        "local_filing": False,
        "transcript": False,
        "media": True,
        "snippets": True,
    },
}

def _classify_report_type(query: str) -> str:
    q = _safe_str(query).strip().lower()
    technical_tokens = (
        "technical",
        "macd",
        "rsi",
        "技术分析",
        "支撑",
        "阻力",
        "趋势",
    )
    news_tokens = (
        "news",
        "新闻",
        "影响分析",
        "事件",
    )
    deep_tokens = (
        "deep report",
        "longform",
        "filing",
        "10-k",
        "10-q",
        "earnings call",
        "transcript",
        "deep research",
        "深度",
        "研报",
        "财报",
        "电话会",
    )
    if any(_token_in_text(token, q) for token in technical_tokens):
        return "technical"
    if any(_token_in_text(token, q) for token in news_tokens):
        return "news"
    if any(_token_in_text(token, q) for token in deep_tokens):
        return "deep_financial"
    return "general"

def _infer_market_from_context(*, tickers: list[str] | None = None, market: str | None = None) -> str:
    market_text = _safe_str(market).strip().upper()
    if market_text in {"US", "CN", "HK"}:
        return market_text

    for ticker in tickers or []:
        symbol = _safe_str(ticker).strip().upper()
        if not symbol:
            continue
        if symbol.endswith((".SS", ".SZ", ".BJ")):
            return "CN"
        if symbol.endswith(".HK"):
            return "HK"
        return "US"
    return "US"

def _build_report_quality_hints(
    *,
    query: str,
    citations: list[dict[str, Any]],
    tickers: list[str] | None = None,
    market: str | None = None,
) -> dict[str, Any]:
    authoritative_media_domains = (
        "reuters.com",
        "bloomberg.com",
        "wsj.com",
        "ft.com",
        "cnbc.com",
        "finance.yahoo.com",
    )
    local_filing_domains = (
        "cninfo.com.cn",
        "sse.com.cn",
        "szse.cn",
        "hkexnews.hk",
        "hkex.com.hk",
    )

    report_type = _classify_report_type(query)
    profile = dict(_QUALITY_PROFILES.get(report_type, _QUALITY_PROFILES["general"]))
    report_market = _infer_market_from_context(tickers=tickers, market=market)
    if report_type == "deep_financial":
        if report_market == "US":
            profile["10k"] = True
            profile["10q"] = True
            profile["local_filing"] = False
        else:
            profile["10k"] = False
            profile["10q"] = False
            profile["local_filing"] = True

    deep_required = report_type == "deep_financial"

    has_10k = False
    has_10q = False
    has_local_filing = False
    has_earnings_transcript = False
    authoritative_media_count = 0
    sec_filing_count = 0
    local_filing_count = 0
    rich_snippet_count = 0

    for item in citations:
        if not isinstance(item, dict):
            continue
        url = _safe_str(item.get("url") or "").strip().lower()
        source = _safe_str(item.get("source") or "").strip().lower()
        title = _safe_str(item.get("title") or "").strip().lower()
        snippet = _safe_str(item.get("snippet") or "").strip()
        parsed = urlparse(url)
        domain = (parsed.hostname or "").lower().removeprefix("www.")  # lstrip 按字符集合剥除，会吃掉 wsj.com 的首字母
        if not domain and url:
            # 无 scheme 的 URL（"sec.gov/Archives/x"）urlparse 整串当 path、hostname=None。
            # 补 scheme 重解析拿 host，取代旧 "sec.gov/" in url 全串子串——
            # 后者会命中任意主机 query 里携带的 sec.gov/（evil.example/?u=sec.gov/x）。
            domain = (urlparse("https://" + url).hostname or "").lower().removeprefix("www.")
        joined = f"{url} {title} {snippet.lower()}"

        # 域名判定按 tools/news.py 同款规范：domain == d 或 endswith("."+d)。
        # 裸 endswith(d) 无点边界——notsec.gov/microsoft.com(⊃ft.com)/notcninfo.com.cn
        # 等仿冒或撞尾主机被计成 SEC filing/权威媒体/本地披露，压制质量缺口。
        if domain == "sec.gov" or domain.endswith(".sec.gov"):
            sec_filing_count += 1
            if re.search(r"\b10-k\b|annual report|form\s*10k", joined, flags=re.I):
                has_10k = True
            if re.search(r"\b10-q\b|quarterly report|form\s*10q", joined, flags=re.I):
                has_10q = True

        if any(domain == d or domain.endswith("." + d) for d in local_filing_domains) or source == "local_disclosure":
            local_filing_count += 1
            has_local_filing = True

        if re.search(r"earnings|conference call|transcript|业绩电话会|电话会纪要", joined, flags=re.I):
            has_earnings_transcript = True

        if any(domain == d or domain.endswith("." + d) for d in authoritative_media_domains):
            authoritative_media_count += 1

        normalized_snippet = snippet.strip().lower()
        if (
            len(snippet) >= 40
            and normalized_snippet
            and normalized_snippet != url
            and not normalized_snippet.startswith("http://")
            and not normalized_snippet.startswith("https://")
        ):
            rich_snippet_count += 1

    missing: list[str] = []
    missing_counts = {"critical": 0, "important": 0, "minor": 0}

    def _append_missing(message: str, severity: str) -> None:
        missing.append(message)
        if severity in missing_counts:
            missing_counts[severity] += 1

    if deep_required:
        if profile.get("10k") and not has_10k:
            _append_missing("缺少可识别的 10-K 引用", "critical")
        if profile.get("10q") and not has_10q:
            _append_missing("缺少可识别的 10-Q 引用", "critical")
        if profile.get("local_filing") and not has_local_filing:
            _append_missing("缺少本地市场披露引用（CN/HK）", "critical")
        if profile.get("transcript") and not has_earnings_transcript:
            _append_missing("缺少业绩电话会纪要/Transcript 引用", "important")
        if profile.get("media") and authoritative_media_count <= 0:
            _append_missing("缺少权威媒体交叉引用（Reuters/Bloomberg/WSJ/FT/CNBC/Yahoo）", "important")
        if profile.get("snippets") and rich_snippet_count < 2:
            _append_missing("证据摘录质量不足（多数仅 URL，缺少正文摘录）", "minor")

    return {
        "deep_report_required": deep_required,
        "report_type": report_type,
        "market": report_market,
        "applied_profile": profile,
        "qualified": not missing,
        "missing_requirements": missing,
        "missing_counts": missing_counts,
        "stats": {
            "citation_count": len(citations),
            "sec_filing_count": sec_filing_count,
            "local_filing_count": local_filing_count,
            "authoritative_media_count": authoritative_media_count,
            "rich_snippet_count": rich_snippet_count,
            "has_10k": has_10k,
            "has_10q": has_10q,
            "has_local_filing": has_local_filing,
            "has_earnings_transcript": has_earnings_transcript,
        },
    }
