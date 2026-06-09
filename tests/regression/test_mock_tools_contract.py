# -*- coding: utf-8 -*-
"""Regression mock contract tests."""

from tests.regression.mocks.mock_tools import MockToolsModule


def test_mock_tools_cover_report_agent_tool_contracts():
    """MockToolsModule should cover tools probed by report-path agents."""
    tools = MockToolsModule()
    required_methods = [
        "_fetch_with_yfinance",
        "_fetch_with_finnhub",
        "_fetch_with_alpha_vantage",
        "_search_for_price",
        "get_option_chain_metrics",
        "get_stock_historical_data",
        "_fetch_with_finnhub_news",
        "_search_company_news",
        "score_news_source_reliability",
        "get_event_calendar",
        "get_authoritative_media_news",
        "search_authoritative_feeds",
        "get_financial_statements",
        "get_company_info",
        "get_earnings_estimates",
        "get_eps_revisions",
        "get_fred_data",
        "get_official_macro_releases",
        "get_market_sentiment",
        "get_economic_events",
        "search",
    ]

    missing = [name for name in required_methods if not callable(getattr(tools, name, None))]

    assert missing == []
