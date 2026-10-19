# -*- coding: utf-8 -*-
"""Tests for resolve_subject three-tier active_symbol binding gate."""

import logging

import pytest

from backend.graph.nodes.resolve_subject import resolve_subject


def _make_state(
    query: str = "",
    active_symbol: str | None = None,
    selections: list | None = None,
) -> dict:
    ui_context: dict = {}
    if active_symbol is not None:
        ui_context["active_symbol"] = active_symbol
    if selections is not None:
        ui_context["selections"] = selections
    return {"query": query, "ui_context": ui_context}


class TestResolveSubjectTierGate:
    """Three-tier active_symbol binding tests."""

    @pytest.mark.asyncio
    async def test_no_active_symbol_stays_unknown(self):
        """Without active_symbol, non-financial query stays unknown."""
        result = await resolve_subject(_make_state(query="你是男的还是女的"))
        subject = result["subject"]
        assert subject["subject_type"] == "unknown"
        assert subject["tickers"] == []

    @pytest.mark.asyncio
    async def test_tier1_explicit_ticker_in_query(self):
        """Explicit ticker in query always wins (Tier 1)."""
        result = await resolve_subject(_make_state(query="分析 AAPL", active_symbol="GOOGL"))
        subject = result["subject"]
        # extract_tickers should find AAPL in the query
        if subject["subject_type"] == "company":
            assert "AAPL" in subject["tickers"]
            assert subject["binding_tier"] == "tier1_explicit_ticker"

    @pytest.mark.asyncio
    async def test_tier2_keyword_binds(self):
        """Clear financial keyword + active_symbol → bind (Tier 2)."""
        result = await resolve_subject(_make_state(query="股价怎么样", active_symbol="AAPL"))
        subject = result["subject"]
        assert subject["subject_type"] == "company"
        assert subject["tickers"] == ["AAPL"]
        assert subject["binding_tier"] == "tier2_keyword"

    @pytest.mark.asyncio
    async def test_non_financial_no_active_symbol(self):
        """Non-financial query without active_symbol stays unknown."""
        result = await resolve_subject(_make_state(query="你是男的还是女的"))
        subject = result["subject"]
        assert subject["subject_type"] == "unknown"
        assert subject["binding_tier"] == "none"

    @pytest.mark.asyncio
    async def test_empty_query_no_binding(self):
        """Empty query never triggers active_symbol binding."""
        result = await resolve_subject(_make_state(query="", active_symbol="AAPL"))
        subject = result["subject"]
        assert subject["subject_type"] == "unknown"
        assert subject["tickers"] == []

    @pytest.mark.asyncio
    async def test_selection_overrides_all(self):
        """UI selection always takes precedence."""
        selections = [{"id": "news-1", "type": "news"}]
        result = await resolve_subject(
            _make_state(query="分析这个", active_symbol="TSLA", selections=selections)
        )
        subject = result["subject"]
        assert subject["subject_type"] == "news_item"
        assert subject["binding_tier"] == "selection"

    @pytest.mark.asyncio
    async def test_binding_tier_tracked(self):
        """binding_tier field is always present in subject."""
        result = await resolve_subject(_make_state(query="hello", active_symbol="AAPL"))
        subject = result["subject"]
        assert "binding_tier" in subject

    @pytest.mark.asyncio
    async def test_tier1_cn_dotted_symbol_keeps_full_ticker(self):
        """CN dotted symbols (e.g. 600519.SS) should not be truncated to suffix."""
        result = await resolve_subject(_make_state(query="分析 600519.SS 的估值", active_symbol="AAPL"))
        subject = result["subject"]
        assert subject["subject_type"] == "company"
        assert "600519.SS" in subject["tickers"]
        assert "SS" not in subject["tickers"]

    @pytest.mark.asyncio
    async def test_tier1_extraction_failure_is_not_a_measured_nonexplicit_query(
        self, monkeypatch, caplog
    ):
        """`extract_tickers` 抛异常被 `except Exception: pass` 吞掉后，tickers 恒空，
        subject 回落成 unknown —— 一次抽取故障被渲染成"这个 query 里没有明确标的"
        这一查询事实（项目规则 2、finsight-silent-success-forbidden）。
        降级可以保留，但必须留下可定位的 warning。
        """
        import backend.config.ticker_mapping as ticker_mapping

        monkeypatch.setattr(
            ticker_mapping,
            "extract_tickers",
            lambda _query: (_ for _ in ()).throw(RuntimeError("alias table unavailable")),
        )

        with caplog.at_level(logging.WARNING):
            result = await resolve_subject(
                _make_state(query="分析 AAPL", active_symbol="GOOGL")
            )

        subject = result["subject"]
        # Tier-1 抽不到（AAPL）时不再有明确标的，只能靠 active_symbol 绑定
        assert subject["binding_tier"] == "tier2_keyword"
        assert subject["tickers"] == ["GOOGL"]
        # 抽取挂了导致 tier1 结论缺失必须留下痕迹，且日志不得回显用户 query
        assert "[resolve_subject] Tier-1 ticker extraction failed" in caplog.text
        assert "AAPL" not in caplog.text
