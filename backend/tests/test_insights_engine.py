# -*- coding: utf-8 -*-
"""Tests for Dashboard Insights Engine — Scorers, Orchestrator, Prompts."""

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.dashboard.cache import DashboardCache
from backend.dashboard.insights_engine import (
    DashboardScorer,
    DigestAgent,
    FinancialScorer,
    FinancialDigest,
    InsightsOrchestrator,
    NewsScorer,
    NewsDigest,
    OverviewScorer,
    OverviewDigest,
    PeersScorer,
    PeersDigest,
    TechnicalScorer,
    TechnicalDigest,
    _compute_cache_age,
    _deserialize_insights,
    _ensure_str_list,
    _label_from_score,
    get_insights_orchestrator,
)
from backend.dashboard.insights_prompts import (
    build_financial_prompt,
    build_news_prompt,
    build_overview_prompt,
    build_peers_prompt,
    build_technical_prompt,
)
from backend.dashboard.insights_scorer import (
    _clip_contribution,
    clamp_score,
    score_financial,
    score_news,
    score_overview,
    score_peers,
    score_technical,
)
from backend.dashboard.schemas import DashboardInsightsResponse, InsightCard


@pytest.mark.parametrize("include_company", [False, True])
def test_peer_target_identification_accepts_ticker_alias_without_self_comparison(include_company):
    from backend.dashboard.insights_scorer import metrics_peers, score_peers_details
    target = {"ticker": " aapl ", "trailing_pe": 20.0, "revenue_growth": 0.2}
    peer = {"ticker": "MSFT", "trailing_pe": 30.0, "revenue_growth": 0.1}
    data = {"peers": [target, peer]}
    if include_company:
        data["company"] = target
    else:
        data["subject_symbol"] = " aapl "
    expected = {"subject_symbol": "AAPL",
                "company": {"symbol": "AAPL", "trailing_pe": 20.0, "revenue_growth": 0.2},
                "peers": [{"symbol": "MSFT", "trailing_pe": 30.0, "revenue_growth": 0.1}]}
    assert score_peers_details(data) == score_peers_details(expected)
    assert metrics_peers(data) == metrics_peers(expected)


@pytest.mark.parametrize("field", ["symbol", "ticker"])
def test_repeated_identified_peers_do_not_weight_comparison_or_sample_size(field):
    from backend.dashboard.insights_scorer import metrics_peers, score_peers_details
    company = {"symbol": "AAPL", "trailing_pe": 20.0}
    peers = [{field: "MSFT", "trailing_pe": 10.0}, {field: "GOOG", "trailing_pe": 30.0}]
    expected = {"company": company, "peers": peers}
    repeated = {"company": company, "peers": [peers[0], {**peers[0], field: " msft "}, peers[1]]}
    assert score_peers_details(repeated) == score_peers_details(expected)
    assert metrics_peers(repeated) == metrics_peers(expected)


@pytest.mark.parametrize("field", ["symbol", "ticker"])
def test_company_identity_must_match_peer_comparison_subject(field):
    from backend.dashboard.insights_scorer import metrics_peers, score_peers_details
    target = {"symbol": " aapl ", "trailing_pe": 20.0, "revenue_growth": 0.2}
    peer = {"symbol": "MSFT", "trailing_pe": 30.0, "revenue_growth": 0.1}
    data = {"subject_symbol": "AAPL", "company": {field: "MSFT", "trailing_pe": 100.0,
                                                "revenue_growth": -0.2}, "peers": [target, peer]}
    expected = {"subject_symbol": "AAPL", "company": target, "peers": [peer]}
    assert score_peers_details(data) == score_peers_details(expected)
    assert metrics_peers(data) == metrics_peers(expected)
    assert score_peers_details({"subject_symbol": " aapl ", "company": {**target, field: " aapl "},
                               "peers": [peer]}) == score_peers_details(expected)


@pytest.mark.parametrize("failure", [{"success": False}, {"error": "bad"}, {"status": " Failed "}])
def test_failed_company_and_peer_rows_cannot_supply_comparison_values(failure):
    from backend.dashboard.insights_scorer import metrics_peers, score_peers_details
    company = {"symbol": "AAPL", "trailing_pe": 20.0, "revenue_growth": 0.2, "profit_margin": 0.2}
    peer = {"symbol": "MSFT", "trailing_pe": 30.0, "revenue_growth": 0.1, "profit_margin": 0.1}
    expected = {"company": company, "peers": [peer]}
    mixed = {"company": company, "peers": [
        {"symbol": "BAD", "trailing_pe": 1.0, "revenue_growth": 1.0, "profit_margin": 1.0, **failure},
        peer,
    ]}
    assert score_peers_details(mixed) == score_peers_details(expected)
    assert metrics_peers(mixed) == metrics_peers(expected)
    failed_company = {"subject_symbol": "AAPL", "company": {**company, **failure}, "peers": [peer]}
    assert score_peers_details(failed_company) == score_peers_details({"peers": [peer]})
    assert metrics_peers(failed_company) == metrics_peers({"peers": [peer]})


@pytest.mark.parametrize("failure", [{"success": False}, {"error": "bad"}, {"status": " Failed "}])
def test_failed_news_cannot_change_sentiment_or_hide_valid_duplicate(failure):
    from backend.dashboard.insights_scorer import metrics_news, score_news_details
    valid = {"title": "shares surge", "url": "https://example.invalid/news"}
    data = {"impact": [{"title": "shares drop", "url": valid["url"], **failure}],
            "market": [valid]}
    assert score_news_details(data) == score_news_details({"market": [valid]})
    assert metrics_news(data) == [{"label": "新闻数量", "value": "1"}]
    failed_envelope = {"market": [valid], **failure}
    assert score_news_details(failed_envelope) == score_news_details({})
    assert metrics_news(failed_envelope) == []


@pytest.mark.parametrize("failure", [{"success": False}, {"error": "bad"}, {"status": " Failed "}])
def test_failed_indicator_and_financial_payloads_cannot_supply_scores_or_metrics(failure):
    from backend.dashboard.insights_scorer import (
        metrics_financial, metrics_technical, score_financial_details, score_technical_details,
    )
    technical = {"rsi": 55.0, "trend": "bullish", "ma20": 120.0, "ma50": 100.0, **failure}
    financial = {"trailing_pe": 10.0, "revenue_growth": 0.2, "net_income": 100.0,
                 "debt_to_equity": 0.1, "free_cash_flow": 100.0, **failure}
    nested = {"valuation": {"trailing_pe": 10.0, **failure},
              "financials": {"revenue_growth": 0.2, "net_income": 100.0,
                             "debt_to_equity": 0.1, "free_cash_flow": 100.0, **failure}}
    assert score_technical_details(technical) == score_technical_details({})
    assert metrics_technical(technical) == []
    for data in (financial, nested):
        assert score_financial_details(data) == score_financial_details({})
        assert metrics_financial(data) == []
    assert score_financial({"trailing_pe": 10.0, **nested})[0] == 6.0


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

class TestHelpers:
    """Tests for module-level helper functions."""

    def test_percentage_formatting_does_not_emit_infinite_metrics(self):
        from backend.dashboard.insights_scorer import _fmt_float
        assert _fmt_float(1e308, pct=True) is None
        assert _fmt_float(-1e308, pct=True) is None
        assert _fmt_float(0.125, pct=True) == "12.50%"

    def test_unrepresentable_metric_numbers_do_not_crash_formatting(self):
        from backend.dashboard.insights_scorer import _fmt_float, _fmt_int
        assert _fmt_float(10 ** 400) is None
        assert _fmt_int(10 ** 400) is None

    def test_label_from_score_strong(self):
        assert _label_from_score(9.0) == "强势"

    def test_label_from_score_bullish(self):
        assert _label_from_score(7.0) == "偏多"

    def test_label_from_score_neutral(self):
        assert _label_from_score(5.0) == "中性"

    def test_label_from_score_bearish(self):
        assert _label_from_score(3.5) == "偏空"

    def test_label_from_score_weak(self):
        assert _label_from_score(2.0) == "弱势"

    def test_ensure_str_list_normal(self):
        assert _ensure_str_list(["a", "b"]) == ["a", "b"]

    def test_ensure_str_list_non_list(self):
        assert _ensure_str_list("not a list") == []

    def test_ensure_str_list_mixed(self):
        assert _ensure_str_list([1, None, "ok", "", 3.5]) == ["1", "ok", "3.5"]

    def test_compute_cache_age_valid(self):
        now_iso = datetime.now(timezone.utc).isoformat()
        age = _compute_cache_age(now_iso)
        assert 0 <= age < 2  # within 2 seconds

    def test_compute_cache_age_empty(self):
        assert _compute_cache_age("") == 0

    def test_compute_cache_age_invalid(self):
        assert _compute_cache_age("not-a-date") == 0

    def test_deserialize_insights_valid(self):
        card_data = {
            "agent_name": "test",
            "tab": "overview",
            "score": 7.0,
            "score_label": "偏多",
            "summary": "test summary",
            "key_points": ["point1"],
            "risks": ["risk1"],
            "confidence": 0.8,
            "as_of": "2025-01-01T00:00:00+00:00",
            "model_generated": True,
        }
        result = _deserialize_insights({"overview": card_data})
        assert "overview" in result
        assert isinstance(result["overview"], InsightCard)
        assert result["overview"].score == 7.0
        assert result["overview"].scorer_name is None

    def test_deserialize_insights_invalid_skips(self):
        result = _deserialize_insights({"bad": {"score": "not-a-number"}})
        assert "bad" not in result

    def test_deserialize_insights_non_dict(self):
        result = _deserialize_insights({"x": "not a dict"})
        assert len(result) == 0


class TestNamingCompatibility:
    """Phase 1 compatibility checks for Agent→Scorer semantic refactor."""

    def test_base_alias_points_to_same_class(self):
        assert DashboardScorer is DigestAgent

    def test_concrete_aliases_point_to_same_class(self):
        assert TechnicalScorer is TechnicalDigest
        assert FinancialScorer is FinancialDigest
        assert NewsScorer is NewsDigest
        assert PeersScorer is PeersDigest
        assert OverviewScorer is OverviewDigest

    def test_legacy_identifiers_remain_stable(self):
        assert TechnicalScorer.AGENT_NAME == "technical_digest"
        assert FinancialScorer.AGENT_NAME == "financial_digest"
        assert NewsScorer.AGENT_NAME == "news_digest"
        assert PeersScorer.AGENT_NAME == "peers_digest"
        assert OverviewScorer.AGENT_NAME == "overview_digest"


# ---------------------------------------------------------------------------
# insights_scorer
# ---------------------------------------------------------------------------

class TestClampScore:
    """Tests for clamp_score utility."""

    def test_clamp_within_range(self):
        assert clamp_score(5.0) == 5.0

    def test_clamp_below_min(self):
        assert clamp_score(-2.0) == 1.0

    def test_clamp_above_max(self):
        assert clamp_score(15.0) == 10.0

    def test_clamp_rounds_to_one_decimal(self):
        assert clamp_score(5.555) == 5.6

    def test_clamp_boundary_min(self):
        assert clamp_score(1.0) == 1.0

    def test_clamp_boundary_max(self):
        assert clamp_score(10.0) == 10.0

    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), "bad", True, False])
    def test_clamp_non_finite_or_invalid_is_neutral(self, value):
        assert clamp_score(value) == 5.0

    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), "bad", True, False])
    def test_contribution_non_finite_or_invalid_is_neutral(self, value):
        assert _clip_contribution(value) == 0.0


def test_metric_formatters_reject_boolean_values():
    from backend.dashboard.insights_scorer import _fmt_float, _fmt_int

    assert _fmt_float(True) is None
    assert _fmt_float(False) is None
    assert _fmt_int(True) is None
    assert _fmt_int(False) is None


class TestScoreTechnical:
    @pytest.mark.parametrize("trend, expected", [("BULLISH", 7.0), (" downtrend ", 4.0)])
    def test_trend_score_and_factors_use_same_normalization(self, trend, expected):
        from backend.dashboard.insights_scorer import score_technical_details
        score, _, _, details = score_technical_details({"trend": trend})
        assert score == expected
        contribution = next(row for row in details if row["factor_key"] == "trend_direction")["contribution"]
        assert (contribution > 0) == (expected > 5)
        assert contribution != 0

    def test_equal_macd_and_signal_have_no_bearish_contribution(self):
        from backend.dashboard.insights_scorer import score_technical_details
        score, _, _, details = score_technical_details({"macd": 0.0, "macd_signal": 0.0})
        assert score == 5.0
        assert next(row for row in details if row["factor_key"] == "momentum")["contribution"] == 0.0

    @pytest.mark.parametrize("ma20, ma50", [(0.0, 1.0), (-1.0, -2.0)])
    def test_nonpositive_moving_averages_are_unavailable(self, ma20, ma50):
        from backend.dashboard.insights_scorer import metrics_technical, score_technical_details
        data = {"ma20": ma20, "ma50": ma50}
        score, _, points, details = score_technical_details(data)
        assert score == 5.0
        assert not points
        assert next(row for row in details if row["factor_key"] == "momentum")["contribution"] == 0.0
        assert not any(row["label"] == "MA20" for row in metrics_technical(data))

    def test_equal_moving_averages_are_neutral(self):
        from backend.dashboard.insights_scorer import score_technical_details
        score, _, points, details = score_technical_details({"ma20": 100.0, "ma50": 100.0})
        assert score == 5.0
        assert not any("死叉" in point for point in points)
        assert next(row for row in details if row["factor_key"] == "momentum")["contribution"] == 0.0

    @pytest.mark.parametrize("rsi", [-1.0, 101.0])
    def test_out_of_range_rsi_is_unavailable(self, rsi):
        from backend.dashboard.insights_scorer import metrics_technical, score_technical_details
        score, _, points, details = score_technical_details({"rsi": rsi})
        assert score == 5.0
        assert not any("RSI" in point for point in points)
        assert next(row for row in details if row["factor_key"] == "rsi_state")["contribution"] == 0.0
        assert not any(row["label"] == "RSI" for row in metrics_technical({"rsi": rsi}))

    """Tests for deterministic technical scoring."""

    def test_empty_data_returns_neutral(self):
        score, label, points = score_technical({})
        assert 4.0 <= score <= 6.0
        assert isinstance(points, list)

    def test_bullish_signals(self):
        data = {
            "rsi": 55.0,
            "trend": "bullish",
            "ma20": 200.0,
            "ma50": 180.0,
            "macd": 2.0,
            "macd_signal": 1.0,
        }
        score, label, points = score_technical(data)
        assert score >= 7.0
        assert len(points) >= 3

    def test_bearish_signals(self):
        data = {
            "rsi": 75.0,
            "trend": "bearish",
            "ma20": 150.0,
            "ma50": 180.0,
        }
        score, label, points = score_technical(data)
        assert score <= 5.0

    def test_rsi_oversold(self):
        data = {"rsi": 25.0}
        score, label, points = score_technical(data)
        assert any("超卖" in p for p in points)

    def test_rsi_overbought(self):
        data = {"rsi": 80.0}
        score, label, points = score_technical(data)
        assert any("超买" in p for p in points)


class TestScoreFinancial:
    """Tests for deterministic financial scoring."""

    @pytest.mark.parametrize("field,group,nested_value", [
        ("debt_to_equity", "financials", 2.0),
        ("revenue_growth", "financials", 0.5),
        ("free_cash_flow", "financials", 100.0),
        ("net_income", "financials", 100.0),
        ("trailing_pe", "valuation", 20.0),
    ])
    def test_explicit_zero_financials_are_not_replaced_by_nested_values(self, field, group, nested_value):
        from backend.dashboard.insights_scorer import metrics_financial, score_financial_details

        primary = {field: 0.0}
        mixed = {field: 0.0, group: {field: nested_value}}
        assert score_financial(mixed) == score_financial(primary)
        assert score_financial_details(mixed) == score_financial_details(primary)
        assert metrics_financial(mixed) == metrics_financial(primary)
        if field in {"debt_to_equity", "revenue_growth", "trailing_pe"}:
            assert metrics_financial(primary)[0]["value"] in {"0.00", "0.00%"}

    def test_empty_data_returns_base(self):
        score, label, points = score_financial({})
        assert score == 4.0

    def test_zero_growth_profit_and_cashflow_are_not_negative_measurements(self):
        from backend.dashboard.insights_scorer import score_financial_details

        data = {"revenue_growth": 0.0, "net_income": 0.0, "free_cash_flow": 0.0}
        score, _, points, breakdown = score_financial_details(data)
        assert score == 4.0
        assert not any("下降" in point or "为负" in point for point in points)
        factors = {row["factor_key"]: row for row in breakdown}
        assert factors["growth"]["contribution"] == 0.0
        assert factors["cash_flow"]["contribution"] == 0.0

        negative, _, negative_points = score_financial({"revenue_growth": -0.1, "net_income": -10})
        assert negative < score
        assert any("下降" in point or "为负" in point for point in negative_points)

    @pytest.mark.parametrize("pe", [-10.0, 0.0])
    def test_non_positive_pe_cannot_supply_a_valuation_advantage(self, pe):
        from backend.dashboard.insights_scorer import metrics_peers, score_financial_details, score_peers_details

        financial = score_financial_details({"trailing_pe": pe})
        valuation = next(row for row in financial[3] if row["factor_key"] == "valuation")
        assert valuation["contribution"] == 0.0

        peer_data = {"company": {"trailing_pe": pe}, "peers": [{"trailing_pe": 20.0}]}
        assert score_peers_details(peer_data)[0] == 5.0
        comparison = {"company": {"trailing_pe": 20.0}, "peers": [{"trailing_pe": pe}, {"trailing_pe": 30.0}]}
        assert score_peers_details(comparison)[0] == 6.0
        average = next(row for row in metrics_peers(comparison) if row["label"] == "行业均值PE")
        assert average["value"] == "30.0"

    def test_negative_debt_to_equity_is_not_rewarded_as_financial_strength(self):
        from backend.dashboard.insights_scorer import metrics_financial, score_financial_details

        score, _, points, breakdown = score_financial_details({"debt_to_equity": -1.0})
        assert score == 4.0
        assert not any("财务稳健" in point for point in points)
        leverage = next(row for row in breakdown if row["factor_key"] == "balance_sheet")
        assert leverage["contribution"] == 0.0
        assert metrics_financial({"debt_to_equity": -1.0})[0]["label"] == "债务权益比"
        assert score_financial({"debt_to_equity": 0.0})[0] == 5.0

    def test_healthy_company(self):
        data = {
            "trailing_pe": 20.0,
            "revenue_growth": 0.15,
            "net_income": 1_000_000,
            "debt_to_equity": 0.3,
            "free_cash_flow": 500_000,
        }
        score, label, points = score_financial(data)
        assert score >= 8.0
        assert len(points) >= 4

    def test_distressed_company(self):
        data = {
            "trailing_pe": 50.0,
            "net_income": -100_000,
            "revenue_growth": -0.2,
            "debt_to_equity": 2.0,
        }
        score, label, points = score_financial(data)
        assert score <= 4.0

    def test_nested_valuation_pe(self):
        """PE can be nested under 'valuation' key."""
        data = {"valuation": {"trailing_pe": 15.0}}
        score, label, points = score_financial(data)
        assert any("市盈率" in p for p in points)


class TestScoreNews:
    """Tests for deterministic news scoring."""

    @pytest.mark.parametrize("title, expected", [("Stock surges", 7.0), ("Stock dropped", 3.0), ("Analyst upgraded shares", 7.0)])
    def test_english_sentiment_still_accepts_common_word_forms(self, title, expected):
        assert score_news({"market": [{"title": title}]})[0] == expected

    @pytest.mark.parametrize("title", ["Company discloses transmission schedule", "Buyer attends meeting", "Recordkeeping policy published"])
    def test_english_sentiment_keywords_do_not_match_unrelated_substrings(self, title):
        from backend.dashboard.insights_scorer import score_news_details
        score, _, _, details = score_news_details({"market": [{"title": title}]})
        assert score == 5.0
        assert next(row for row in details if row["factor_key"] == "sentiment_balance")["value"] == 0.0

    def test_invalid_news_entries_do_not_dilute_sentiment_or_sample_size(self):
        from backend.dashboard.insights_scorer import metrics_news, score_news_details
        data = {"market": [{"title": "surge"}, None, 42, {"title": " "}, {"title": {"risk": True}}]}
        score, _, points, details = score_news_details(data)
        assert score == 7.0
        assert "近期 1 条新闻" in points[0]
        assert metrics_news(data) == [{"label": "新闻数量", "value": "1"}]
        assert next(row for row in details if row["factor_key"] == "sentiment_balance")["value"] == 1.0

    def test_same_article_in_market_and_impact_counts_once(self):
        from backend.dashboard.insights_scorer import metrics_news, score_news_details
        article = {"title": "surge", "url": "https://example.test/story"}
        data = {"market": [article, {"title": "Company publishes schedule"}], "impact": [dict(article)]}
        score, _, points, details = score_news_details(data)
        assert score == 6.0
        assert "近期 2 条新闻" in points[0]
        assert metrics_news(data) == [{"label": "新闻数量", "value": "2"}]
        assert next(row for row in details if row["factor_key"] == "impact_ratio")["value"] == 0.5

    def test_no_news(self):
        score, label, points = score_news({})
        assert score == 5.0
        assert "暂无近期新闻数据" in points[0]

    def test_positive_news(self):
        data = {
            "market": [
                {"title": "Stock surges on record earnings", "summary": "beat expectations"},
                {"title": "Analyst upgrade to buy", "summary": "bullish outlook"},
                {"title": "Company breakthrough", "summary": "positive"},
            ],
            "impact": [],
        }
        score, label, points = score_news(data)
        assert score >= 6.0

    def test_negative_news(self):
        data = {
            "market": [
                {"title": "Stock drops on downgrade", "summary": "risk of sell-off"},
                {"title": "Bearish outlook", "summary": "risk factors increase"},
            ],
            "impact": [],
        }
        score, label, points = score_news(data)
        assert score <= 5.0

    def test_mixed_news(self):
        data = {
            "market": [
                {"title": "surge", "summary": "positive"},
                {"title": "drop risk", "summary": "bearish"},
            ],
        }
        score, label, points = score_news(data)
        assert 3.0 <= score <= 7.0


class TestScorePeers:
    """Tests for deterministic peer scoring."""

    def test_large_finite_peer_averages_do_not_overflow(self):
        from backend.dashboard.insights_scorer import metrics_peers, score_peers_details
        data = {"company": {"trailing_pe": 1e308, "revenue_growth": 1e308},
                "peers": [{"trailing_pe": 1e308, "revenue_growth": 1e308}] * 2}
        score, _, points, details = score_peers_details(data)
        assert score == 5.0
        assert not any("低于行业" in point for point in points)
        assert next(row for row in details if row["factor_key"] == "peer_valuation_gap")["contribution"] == 0.0
        assert not any("inf" in row["value"].lower() for row in metrics_peers(data))

    @pytest.mark.parametrize("pe", [18.0, 20.0, 22.0])
    def test_peer_valuation_breakdown_respects_neutral_band(self, pe):
        from backend.dashboard.insights_scorer import score_peers_details
        score, _, _, details = score_peers_details({"company": {"trailing_pe": pe}, "peers": [{"trailing_pe": 20.0}]})
        assert score == 5.0
        assert next(row for row in details if row["factor_key"] == "peer_valuation_gap")["contribution"] == 0.0

    @pytest.mark.parametrize("growth", [0.0, 0.2, -0.2])
    def test_equal_peer_growth_is_neutral(self, growth):
        from backend.dashboard.insights_scorer import score_peers_details
        data = {"company": {"revenue_growth": growth}, "peers": [{"revenue_growth": growth}]}
        score, _, points, details = score_peers_details(data)
        assert score == 5.0
        assert not any("低于行业" in point for point in points)
        assert next(row for row in details if row["factor_key"] == "peer_growth_gap")["contribution"] == 0.0

    def test_net_margin_from_dashboard_is_used_for_profit_comparison(self):
        data = {"subject_symbol": "AAPL", "peers": [
            {"symbol": "AAPL", "net_margin": 0.3},
            {"symbol": "MSFT", "net_margin": 0.1},
        ]}
        score, _, points = score_peers(data)
        assert score == 6.0
        assert "利润率优于行业平均水平" in points

    @pytest.mark.asyncio
    async def test_peer_card_uses_target_row_from_real_dashboard_payload(self):
        data = {"subject_symbol": "AAPL", "peers": [
            {"symbol": " aapl ", "trailing_pe": 10.0},
            {"symbol": "MSFT", "trailing_pe": 30.0},
        ]}
        with patch("backend.dashboard.scorers._get_llm", return_value=None):
            card = await PeersDigest().digest("AAPL", data)

        assert card.score == 6.0
        metrics = {row["label"]: row["value"] for row in card.key_metrics}
        assert metrics["公司PE"] == "10.00"
        assert metrics["行业均值PE"] == "30.0"
        assert metrics["对比公司数"] == "1"

    def test_no_peers(self):
        score, label, points = score_peers({})
        assert score == 5.0
        assert "暂无同行对比数据" in points[0]

    def test_outperforming_peers(self):
        data = {
            "company": {"trailing_pe": 12.0, "revenue_growth": 0.25, "profit_margin": 0.2},
            "peers": [
                {"trailing_pe": 20.0, "revenue_growth": 0.1, "profit_margin": 0.1},
                {"trailing_pe": 25.0, "revenue_growth": 0.08, "profit_margin": 0.12},
            ],
        }
        score, label, points = score_peers(data)
        assert score >= 7.0

    def test_underperforming_peers(self):
        data = {
            "company": {"trailing_pe": 40.0, "revenue_growth": -0.05},
            "peers": [
                {"trailing_pe": 15.0, "revenue_growth": 0.15},
                {"trailing_pe": 18.0, "revenue_growth": 0.12},
            ],
        }
        score, label, points = score_peers(data)
        assert score <= 5.0


class TestScoreOverview:
    """Tests for composite overview scoring."""

    def test_neutral_scores(self):
        score, label, points = score_overview(
            tech_score=5.0, fin_score=5.0, news_score=5.0, peers_score=5.0
        )
        assert score == 5.0
        assert any("中性" in p for p in points)

    def test_bullish_scores(self):
        score, label, points = score_overview(
            tech_score=9.0, fin_score=9.0, news_score=8.0, peers_score=8.0
        )
        assert score >= 8.0
        assert any("偏多" in p for p in points)

    def test_weighted_average(self):
        """financial 35%, technical 25%, news 20%, peers 20%."""
        score, _, _ = score_overview(
            tech_score=10.0, fin_score=10.0, news_score=10.0, peers_score=10.0
        )
        assert score == 10.0


# ---------------------------------------------------------------------------
# insights_prompts
# ---------------------------------------------------------------------------

class TestPrompts:
    """Tests for prompt template builders."""

    def test_build_technical_prompt(self):
        prompt = build_technical_prompt("AAPL", {"rsi": 55.0, "trend": "bullish"})
        assert "AAPL" in prompt
        assert "技术分析" in prompt
        assert "JSON" in prompt

    def test_build_financial_prompt(self):
        prompt = build_financial_prompt("AAPL", {"trailing_pe": 28.5})
        assert "AAPL" in prompt
        assert "财务" in prompt

    def test_build_news_prompt(self):
        prompt = build_news_prompt("TSLA", {"market": [{"title": "test"}]})
        assert "TSLA" in prompt
        assert "新闻" in prompt

    def test_build_peers_prompt(self):
        prompt = build_peers_prompt("MSFT", {"peers": [{"symbol": "GOOG"}]})
        assert "MSFT" in prompt
        assert "同行" in prompt

    def test_build_overview_prompt_with_sub_scores(self):
        prompt = build_overview_prompt(
            "NVDA",
            {"valuation": {"trailing_pe": 50}},
            sub_scores={"technical": 7.0, "financial": 6.5, "news": 5.0, "peers": 6.0},
        )
        assert "NVDA" in prompt
        assert "7.0" in prompt
        assert "6.5" in prompt

    def test_build_overview_prompt_without_sub_scores(self):
        prompt = build_overview_prompt("AAPL", {}, sub_scores=None)
        assert "AAPL" in prompt
        assert "dimension_scores" not in prompt

    def test_truncate_data_in_prompt(self):
        """Large data should be truncated."""
        large_data = {"key": "x" * 5000}
        prompt = build_technical_prompt("TEST", large_data)
        assert "truncated" in prompt


# ---------------------------------------------------------------------------
# DigestAgent (base class)
# ---------------------------------------------------------------------------

class TestDigestAgent:
    """Tests for DigestAgent base class via TechnicalDigest."""

    def test_llm_initialization_error_log_is_redacted(self, monkeypatch, caplog):
        import backend.dashboard.scorers as scorers
        import backend.llm_config as llm_config

        secret = "PRIVATE postgres://insights:secret@db/llm"
        monkeypatch.setattr(scorers, "_llm_instance", None)
        monkeypatch.setattr(scorers, "_llm_init_attempted", False)
        monkeypatch.setattr(
            llm_config,
            "create_llm",
            lambda **_kwargs: (_ for _ in ()).throw(RuntimeError(secret)),
        )

        assert scorers._get_llm() is None
        assert secret not in caplog.text
        assert "[Insights] LLM init failed; dashboard scorers will use fallback" in caplog.text

    @pytest.mark.asyncio
    async def test_digest_llm_unavailable_uses_fallback(self):
        """When LLM is None, should use deterministic fallback."""
        agent = TechnicalDigest()
        data = {"rsi": 55.0, "trend": "bullish"}

        with patch("backend.dashboard.scorers._get_llm", return_value=None):
            card = await agent.digest("AAPL", data)

        assert isinstance(card, InsightCard)
        assert card.agent_name == "technical_digest"
        assert card.scorer_name == "technical_scorer"
        assert card.tab == "technical"
        assert card.model_generated is False
        assert card.confidence == 0.4
        assert 1.0 <= card.score <= 10.0
        assert len(card.score_breakdown) >= 3

    @pytest.mark.asyncio
    async def test_digest_llm_success(self):
        """When LLM returns valid JSON, should parse correctly."""
        agent = TechnicalDigest()
        data = {"rsi": 55.0}

        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "score": 7.5,
            "score_label": "偏多",
            "summary": "RSI 55 处于正常区间，技术面整体偏多。",
            "key_points": ["RSI 正常", "均线多头"],
            "risks": ["上方阻力"],
        })
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        with patch("backend.dashboard.scorers._get_llm", return_value=mock_llm):
            card = await agent.digest("AAPL", data)

        assert isinstance(card, InsightCard)
        assert card.model_generated is True
        assert card.scorer_name == "technical_scorer"
        assert card.confidence == 0.8
        assert card.score_label == "偏多"
        assert len(card.key_points) == 2
        assert len(card.risks) == 1
        assert len(card.score_breakdown) >= 3

    @pytest.mark.asyncio
    async def test_digest_llm_timeout_falls_back(self):
        """When LLM times out, should use deterministic fallback."""
        agent = TechnicalDigest()
        data = {"rsi": 55.0}

        mock_llm = AsyncMock()

        async def slow_invoke(_prompt):
            await asyncio.sleep(100)

        mock_llm.ainvoke = slow_invoke

        with patch("backend.dashboard.scorers._get_llm", return_value=mock_llm):
            with patch("backend.dashboard.scorers._DIGEST_TIMEOUT_SECONDS", 0.01):
                card = await agent.digest("AAPL", data)

        assert card.model_generated is False

    @pytest.mark.asyncio
    async def test_digest_llm_error_log_is_redacted(self, caplog):
        secret = "PRIVATE postgres://insights:secret@db/invoke"
        agent = TechnicalDigest()
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError(secret))

        with patch("backend.dashboard.scorers._get_llm", return_value=mock_llm):
            card = await agent.digest("AAPL", {"rsi": 55.0})

        assert card.model_generated is False
        assert secret not in caplog.text
        assert "[Insights] scorer failed" in caplog.text

    @pytest.mark.asyncio
    async def test_digest_llm_returns_invalid_json(self):
        """When LLM returns invalid JSON, should fall back to deterministic."""
        agent = FinancialDigest()
        data = {"trailing_pe": 20.0}

        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "This is not JSON at all"
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        with patch("backend.dashboard.scorers._get_llm", return_value=mock_llm):
            card = await agent.digest("AAPL", data)

        assert card.model_generated is False

    @pytest.mark.asyncio
    async def test_digest_llm_rejects_non_finite_score(self):
        agent = TechnicalDigest()
        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = '{"score": NaN, "score_label": "strong"}'
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        with patch("backend.dashboard.scorers._get_llm", return_value=mock_llm):
            card = await agent.digest("AAPL", {"rsi": 55.0})

        assert card.model_generated is False
        assert card.score != 10.0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("payload", [{}, {"score": None}, {"score": True}, {"score": "bad"}, {"score": "NaN"}])
    async def test_invalid_model_score_uses_rule_fallback_confidence(self, payload):
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content=json.dumps(payload)))
        with patch("backend.dashboard.scorers._get_llm", return_value=mock_llm):
            card = await TechnicalDigest().digest("AAPL", {"rsi": 55.0})

        assert card.model_generated is False
        assert card.confidence == 0.4
        assert card.score_breakdown

    @pytest.mark.asyncio
    @pytest.mark.parametrize("score,label,expected", [(4.0, None, "偏空"), (7.5, "弱势", "偏多"), (10.0, "强势", "偏多")])
    async def test_model_label_matches_the_final_adjusted_score(self, score, label, expected):
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content=json.dumps({"score": score, "score_label": label})))
        with patch("backend.dashboard.scorers._get_llm", return_value=mock_llm):
            card = await TechnicalDigest().digest("AAPL", {})

        assert card.model_generated is True
        assert card.score_label == expected

    @pytest.mark.asyncio
    @pytest.mark.parametrize("shape", ["text_blocks", "fragments", "mixed"])
    async def test_digest_accepts_text_content_blocks(self, shape):
        raw = json.dumps({"score": 7.5})
        content = {
            "text_blocks": [{"type": "text", "text": raw}],
            "fragments": [raw[:5], raw[5:]],
            "mixed": [{"type": "image", "text": "ignored"}, {"type": "output_text", "text": raw}],
        }[shape]
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content=content))
        with patch("backend.dashboard.scorers._get_llm", return_value=mock_llm):
            card = await TechnicalDigest().digest("AAPL", {})

        assert card.model_generated is True
        assert card.score == 7.5

    @pytest.mark.asyncio
    async def test_digest_keeps_zero_metrics_and_trims_empty_labels(self):
        payload = {"score": 7.5, "key_metrics": [
            {"label": " 净流入 ", "value": 0},
            {"label": "增长率", "value": " 0% "},
            {"label": "缺失", "value": None},
            {"label": "   ", "value": "100"},
        ]}
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content=json.dumps(payload)))
        with patch("backend.dashboard.scorers._get_llm", return_value=mock_llm):
            card = await TechnicalDigest().digest("AAPL", {})

        assert card.key_metrics == [{"label": "净流入", "value": "0"}, {"label": "增长率", "value": "0%"}]

    @pytest.mark.asyncio
    async def test_digest_does_not_display_structured_objects_as_prose(self):
        payload = {"score": 7.5, "key_points": [{"wrong": "shape"}, ["nested"], " valid ", "   ", True],
                   "risks": [{"wrong": "shape"}, " risk "]}
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content=json.dumps(payload)))
        with patch("backend.dashboard.scorers._get_llm", return_value=mock_llm):
            card = await TechnicalDigest().digest("AAPL", {})

        assert card.key_points == ["valid"]
        assert card.risks == ["risk"]

    @pytest.mark.asyncio
    async def test_digest_llm_returns_markdown_fenced_json(self):
        """LLM sometimes returns JSON wrapped in markdown fences."""
        agent = NewsDigest()
        data = {"market": [{"title": "Good news"}], "impact": []}

        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = '```json\n{"score": 6.0, "score_label": "中性", "summary": "新闻中性。", "key_points": ["test"], "risks": ["none"]}\n```'
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        with patch("backend.dashboard.scorers._get_llm", return_value=mock_llm):
            card = await agent.digest("AAPL", data)

        assert card.model_generated is True
        assert card.score == 6.0

    @pytest.mark.asyncio
    async def test_digest_score_divergence_averaging(self):
        """When LLM score diverges >3 from deterministic, they should be averaged."""
        agent = TechnicalDigest()
        data = {}  # neutral base → score ~5.0

        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "score": 10.0,  # diverges >3 from base ~5.0
            "score_label": "强势",
            "summary": "Extremely bullish",
            "key_points": ["point"],
            "risks": [],
        })
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        with patch("backend.dashboard.scorers._get_llm", return_value=mock_llm):
            card = await agent.digest("AAPL", data)

        # Should be averaged: (10 + 5) / 2 = 7.5
        assert card.score < 10.0
        assert card.model_generated is True


# ---------------------------------------------------------------------------
# OverviewDigest
# ---------------------------------------------------------------------------

class TestOverviewDigest:
    """Tests for OverviewDigest specific behavior."""

    @pytest.mark.asyncio
    async def test_overview_sub_scores_are_detached_from_caller_mutations(self):
        agent = OverviewDigest()
        scores = {"technical": 7.0, "financial": 6.5, "news": 5.0, "peers": 6.0}
        agent.set_sub_scores(scores)
        scores["financial"] = 1.0

        with patch("backend.dashboard.scorers._get_llm", return_value=None):
            card = await agent.digest("AAPL", {})

        assert card.sub_scores["financial"] == 6.5

    @pytest.mark.asyncio
    async def test_overview_includes_sub_scores(self):
        """Overview card should include sub_scores from dimensions."""
        agent = OverviewDigest()
        agent.set_sub_scores({
            "technical": 7.0,
            "financial": 6.5,
            "news": 5.0,
            "peers": 6.0,
        })

        with patch("backend.dashboard.scorers._get_llm", return_value=None):
            card = await agent.digest("AAPL", {})

        assert card.sub_scores is not None
        assert card.sub_scores["technical"] == 7.0
        assert card.sub_scores["financial"] == 6.5

    @pytest.mark.asyncio
    async def test_overview_deterministic_score(self):
        """Overview deterministic fallback uses weighted average."""
        agent = OverviewDigest()
        agent.set_sub_scores({
            "technical": 8.0,
            "financial": 8.0,
            "news": 8.0,
            "peers": 8.0,
        })

        with patch("backend.dashboard.scorers._get_llm", return_value=None):
            card = await agent.digest("AAPL", {})

        assert card.score == 8.0


# ---------------------------------------------------------------------------
# InsightsOrchestrator
# ---------------------------------------------------------------------------

class TestInsightsOrchestrator:
    """Tests for InsightsOrchestrator caching and parallel execution."""

    @pytest.mark.asyncio
    async def test_generate_with_insights_disabled(self):
        """When INSIGHTS_ENABLED is false, returns empty insights."""
        cache = DashboardCache()
        orchestrator = InsightsOrchestrator(cache=cache)

        with patch("backend.dashboard.insights_engine._INSIGHTS_ENABLED", False):
            response = await orchestrator.generate("AAPL")

        assert isinstance(response, DashboardInsightsResponse)
        assert response.insights == {}
        assert response.cached is False

    @pytest.mark.asyncio
    async def test_background_refresh_error_log_is_redacted(self, caplog):
        secret = "PRIVATE postgres://insights:secret@db/cache"
        orchestrator = InsightsOrchestrator(cache=DashboardCache())

        with patch.object(orchestrator, "_generate_fresh", new=AsyncMock(side_effect=RuntimeError(secret))):
            await orchestrator._refresh_in_background("AAPL")

        assert secret not in caplog.text
        assert "[Insights] Background refresh failed" in caplog.text

    @pytest.mark.asyncio
    async def test_hydration_fetch_error_log_is_redacted(self, caplog):
        secret = "PRIVATE postgres://insights:secret@db/hydration"
        orchestrator = InsightsOrchestrator(cache=DashboardCache())

        def _fail(_symbol):
            raise RuntimeError(secret)

        result = await orchestrator._run_fetch_with_timeout("fetch_news", _fail, "AAPL", timeout=1.0)

        assert result is None
        assert secret not in caplog.text
        assert "[Insights] fetch failed" in caplog.text

    @pytest.mark.asyncio
    async def test_generate_fresh_all_fallback(self):
        """Generate with no LLM produces all fallback cards."""
        cache = DashboardCache()
        # Pre-populate dashboard data cache so orchestrator can read it
        cache.set("AAPL", "technicals", {"rsi": 55.0, "trend": "bullish"})
        cache.set("AAPL", "financials", {"trailing_pe": 20.0})
        cache.set("AAPL", "valuation", {"trailing_pe": 20.0})
        cache.set("AAPL", "news", {"market": [{"title": "test"}], "impact": []})
        cache.set("AAPL", "peers", {"company": {}, "peers": []})
        cache.set("AAPL", "snapshot", {"price": 180.0})

        orchestrator = InsightsOrchestrator(cache=cache)

        with patch("backend.dashboard.scorers._get_llm", return_value=None):
            response = await orchestrator.generate("AAPL", force=True)

        assert response.symbol == "AAPL"
        assert response.cached is False
        assert "overview" in response.insights
        assert "financial" in response.insights
        assert "technical" in response.insights
        assert "news" in response.insights
        assert "peers" in response.insights

        for tab_name, card in response.insights.items():
            assert isinstance(card, InsightCard)
            assert card.model_generated is False
            assert card.scorer_name is not None
            assert card.scorer_name.endswith("_scorer")
            assert 1.0 <= card.score <= 10.0

    @pytest.mark.asyncio
    async def test_generate_uses_cache(self):
        """Second call should return cached result."""
        cache = DashboardCache()
        cache.set("AAPL", "technicals", {"rsi": 55.0})
        cache.set("AAPL", "financials", {})
        cache.set("AAPL", "valuation", {})
        cache.set("AAPL", "news", {"market": [{"title": "cached news"}], "impact": []})
        cache.set("AAPL", "peers", {})
        cache.set("AAPL", "snapshot", {})

        orchestrator = InsightsOrchestrator(cache=cache)

        with patch("backend.dashboard.scorers._get_llm", return_value=None):
            first = await orchestrator.generate("AAPL", force=True)
            second = await orchestrator.generate("AAPL")

        assert first.cached is False
        assert second.cached is True
        assert second.cache_age_seconds >= 0

    @pytest.mark.asyncio
    async def test_generate_force_bypasses_cache(self):
        """force=True should bypass cache and regenerate."""
        cache = DashboardCache()
        cache.set("AAPL", "technicals", {"rsi": 55.0})
        cache.set("AAPL", "financials", {})
        cache.set("AAPL", "valuation", {})
        cache.set("AAPL", "news", {"market": [{"title": "cached news"}], "impact": []})
        cache.set("AAPL", "peers", {})
        cache.set("AAPL", "snapshot", {})

        orchestrator = InsightsOrchestrator(cache=cache)

        with patch("backend.dashboard.scorers._get_llm", return_value=None):
            first = await orchestrator.generate("AAPL", force=True)
            second = await orchestrator.generate("AAPL", force=True)

        assert first.cached is False
        assert second.cached is False

    @pytest.mark.asyncio
    async def test_generate_overview_has_sub_scores(self):
        """Overview card should contain sub_scores from dimensions."""
        cache = DashboardCache()
        cache.set("AAPL", "technicals", {"rsi": 55.0, "trend": "bullish"})
        cache.set("AAPL", "financials", {"trailing_pe": 20.0})
        cache.set("AAPL", "valuation", {"trailing_pe": 20.0})
        cache.set("AAPL", "news", {"market": [{"title": "cached news"}], "impact": []})
        cache.set("AAPL", "peers", {"company": {}, "peers": []})
        cache.set("AAPL", "snapshot", {})

        orchestrator = InsightsOrchestrator(cache=cache)

        with patch("backend.dashboard.scorers._get_llm", return_value=None):
            response = await orchestrator.generate("AAPL", force=True)

        overview = response.insights["overview"]
        assert overview.sub_scores is not None
        assert "technical" in overview.sub_scores
        assert "financial" in overview.sub_scores
        assert "news" in overview.sub_scores
        assert "peers" in overview.sub_scores

    @pytest.mark.asyncio
    async def test_generate_refreshes_cached_no_news_marker_when_news_cache_ready(self):
        """If cached insight says 'no news' but news cache has items, force regeneration."""
        cache = DashboardCache()
        cache.set(
            "AAPL",
            "insights",
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "insights": {
                    "news": {
                        "agent_name": "news_digest",
                        "tab": "news",
                        "score": 5.0,
                        "score_label": "中性",
                        "summary": "暂无近期新闻数据",
                        "key_points": ["暂无近期新闻数据"],
                        "risks": [],
                        "confidence": 0.4,
                        "as_of": datetime.now(timezone.utc).isoformat(),
                        "model_generated": False,
                    }
                },
            },
            ttl=cache.TTL_INSIGHTS,
        )
        cache.set(
            "AAPL",
            "news",
            {"market": [{"title": "Positive catalyst"}], "impact": []},
            ttl=cache.TTL_NEWS,
        )

        orchestrator = InsightsOrchestrator(cache=cache)
        fresh_response = DashboardInsightsResponse(
            symbol="AAPL",
            insights={},
            generated_at=datetime.now(timezone.utc).isoformat(),
            cached=False,
            cache_age_seconds=0,
        )

        with patch.object(orchestrator, "_generate_fresh", new=AsyncMock(return_value=fresh_response)) as mock_generate:
            response = await orchestrator.generate("AAPL")

        assert response is fresh_response
        mock_generate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_hydrate_missing_data_fetches_news_and_technicals(self):
        cache = DashboardCache()
        orchestrator = InsightsOrchestrator(cache=cache)
        input_data = {
            "snapshot": {},
            "valuation": {},
            "financials": {},
            "technicals": {},
            "news": {},
            "peers": {},
        }

        with patch.object(
            orchestrator,
            "_fetch_technicals",
            return_value={"rsi": 50.0, "trend": "neutral"},
        ), patch.object(
            orchestrator,
            "_fetch_news",
            return_value={"market": [{"title": "Macro easing"}], "impact": []},
        ):
            hydrated = await orchestrator._hydrate_missing_data("AAPL", input_data)

        assert hydrated["technicals"].get("rsi") == 50.0
        assert len(hydrated["news"].get("market", [])) == 1
        assert cache.get("AAPL", "technicals") is not None
        assert cache.get("AAPL", "news") is not None


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

class TestSingleton:
    """Tests for module-level singleton."""

    def test_get_insights_orchestrator_returns_same_instance(self):
        o1 = get_insights_orchestrator()
        o2 = get_insights_orchestrator()
        assert o1 is o2
        assert isinstance(o1, InsightsOrchestrator)


# ---------------------------------------------------------------------------
# InsightCard Schema
# ---------------------------------------------------------------------------

class TestInsightCardSchema:
    """Tests for InsightCard Pydantic model."""

    def test_valid_card(self):
        card = InsightCard(
            agent_name="test",
            scorer_name="test_scorer",
            tab="technical",
            score=7.5,
            score_label="偏多",
            summary="Test summary",
            key_points=["point1", "point2"],
            risks=["risk1"],
            confidence=0.8,
            as_of="2025-01-01T00:00:00+00:00",
            model_generated=True,
        )
        assert card.score == 7.5
        assert card.model_generated is True
        assert card.scorer_name == "test_scorer"

    def test_score_clamped_by_schema(self):
        """Score must be between 0 and 10."""
        with pytest.raises(Exception):
            InsightCard(
                agent_name="test",
                tab="test",
                score=15.0,
                score_label="invalid",
            )

    def test_card_with_sub_scores(self):
        card = InsightCard(
            agent_name="overview_digest",
            tab="overview",
            score=6.0,
            score_label="中性",
            sub_scores={"technical": 7.0, "financial": 5.0},
        )
        assert card.sub_scores["technical"] == 7.0

    def test_card_serialization(self):
        card = InsightCard(
            agent_name="test",
            tab="test",
            score=5.0,
            score_label="中性",
        )
        data = card.model_dump()
        assert data["agent_name"] == "test"
        assert data["scorer_name"] is None
        assert data["score"] == 5.0
        restored = InsightCard(**data)
        assert restored.score == card.score
