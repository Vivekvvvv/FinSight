import backend.langchain_tools as langchain_tools


def _assert_tool_error_redacted(monkeypatch, dependency_name, tool_name, payload, expected):
    secret = f"PRIVATE https://token@provider.example.com/{tool_name}"
    monkeypatch.setattr(
        langchain_tools,
        dependency_name,
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(secret)),
    )

    result = getattr(langchain_tools, tool_name).invoke(payload)

    assert result == expected
    assert secret not in result


def test_get_stock_price_tool_error_is_redacted(monkeypatch):
    secret = "PRIVATE http://proxy-user:secret@proxy.local/quote"
    monkeypatch.setattr(
        langchain_tools,
        "_get_stock_price",
        lambda _ticker: (_ for _ in ()).throw(RuntimeError(secret)),
    )

    result = langchain_tools.get_stock_price.invoke({"ticker": "AAPL"})

    assert result == "get_stock_price failed"
    assert secret not in result


def test_get_company_news_tool_error_is_redacted(monkeypatch):
    secret = "PRIVATE https://news-token@provider.example.com"
    monkeypatch.setattr(
        langchain_tools,
        "_get_company_news",
        lambda _ticker: (_ for _ in ()).throw(RuntimeError(secret)),
    )

    result = langchain_tools.get_company_news.invoke({"ticker": "AAPL"})

    assert result == "get_company_news failed"
    assert secret not in result


def test_get_company_info_tool_error_is_redacted(monkeypatch):
    secret = "PRIVATE postgres://company:secret@db/info"
    monkeypatch.setattr(
        langchain_tools,
        "_get_company_info",
        lambda _ticker: (_ for _ in ()).throw(RuntimeError(secret)),
    )

    result = langchain_tools.get_company_info.invoke({"ticker": "AAPL"})

    assert result == "get_company_info failed"
    assert secret not in result


def test_search_tool_error_is_redacted(monkeypatch):
    _assert_tool_error_redacted(
        monkeypatch,
        "_search",
        "search",
        {"query": "AAPL earnings"},
        "search failed",
    )


def test_market_sentiment_tool_error_is_redacted(monkeypatch):
    _assert_tool_error_redacted(
        monkeypatch,
        "_get_market_sentiment",
        "get_market_sentiment",
        {},
        "get_market_sentiment failed",
    )


def test_economic_events_tool_error_is_redacted(monkeypatch):
    _assert_tool_error_redacted(
        monkeypatch,
        "_get_economic_events",
        "get_economic_events",
        {},
        "get_economic_events failed",
    )


def test_official_macro_releases_tool_error_is_redacted(monkeypatch):
    _assert_tool_error_redacted(
        monkeypatch,
        "_get_official_macro_releases",
        "get_official_macro_releases",
        {"query": "CPI", "max_results": 5},
        "get_official_macro_releases failed",
    )


def test_performance_comparison_tool_error_is_redacted(monkeypatch):
    _assert_tool_error_redacted(
        monkeypatch,
        "_get_performance_comparison",
        "get_performance_comparison",
        {"tickers": {"AAPL": "Apple"}},
        "get_performance_comparison failed",
    )


def test_historical_drawdowns_tool_error_is_redacted(monkeypatch):
    _assert_tool_error_redacted(
        monkeypatch,
        "_analyze_historical_drawdowns",
        "analyze_historical_drawdowns",
        {"ticker": "AAPL"},
        "analyze_historical_drawdowns failed",
    )


def test_technical_snapshot_tool_error_is_redacted(monkeypatch):
    _assert_tool_error_redacted(
        monkeypatch,
        "_get_stock_historical_data",
        "get_technical_snapshot",
        {"ticker": "AAPL"},
        "get_technical_snapshot failed",
    )


def test_current_datetime_tool_error_is_redacted(monkeypatch):
    _assert_tool_error_redacted(
        monkeypatch,
        "_get_current_datetime",
        "get_current_datetime",
        {},
        "get_current_datetime failed",
    )


def test_earnings_estimates_tool_error_is_redacted(monkeypatch):
    _assert_tool_error_redacted(
        monkeypatch,
        "_get_earnings_estimates",
        "get_earnings_estimates",
        {"ticker": "AAPL"},
        "get_earnings_estimates failed",
    )


def test_eps_revisions_tool_error_is_redacted(monkeypatch):
    _assert_tool_error_redacted(
        monkeypatch,
        "_get_eps_revisions",
        "get_eps_revisions",
        {"ticker": "AAPL"},
        "get_eps_revisions failed",
    )


def test_option_chain_metrics_tool_error_is_redacted(monkeypatch):
    _assert_tool_error_redacted(
        monkeypatch,
        "_get_option_chain_metrics",
        "get_option_chain_metrics",
        {"ticker": "AAPL"},
        "get_option_chain_metrics failed",
    )


def test_factor_exposure_tool_error_is_redacted(monkeypatch):
    _assert_tool_error_redacted(
        monkeypatch,
        "_get_factor_exposure",
        "get_factor_exposure",
        {"positions": [{"ticker": "AAPL", "weight": 1.0}]},
        "get_factor_exposure failed",
    )


def test_portfolio_stress_tool_error_is_redacted(monkeypatch):
    _assert_tool_error_redacted(
        monkeypatch,
        "_run_portfolio_stress_test",
        "run_portfolio_stress_test",
        {"positions": [{"ticker": "AAPL", "weight": 1.0}]},
        "run_portfolio_stress_test failed",
    )


def test_event_calendar_tool_error_is_redacted(monkeypatch):
    _assert_tool_error_redacted(
        monkeypatch,
        "_get_event_calendar",
        "get_event_calendar",
        {"ticker": "AAPL"},
        "get_event_calendar failed",
    )


def test_news_source_reliability_tool_error_is_redacted(monkeypatch):
    _assert_tool_error_redacted(
        monkeypatch,
        "_score_news_source_reliability",
        "score_news_source_reliability",
        {"source": "Reuters"},
        "score_news_source_reliability failed",
    )


def test_authoritative_media_news_tool_error_is_redacted(monkeypatch):
    _assert_tool_error_redacted(
        monkeypatch,
        "_get_authoritative_media_news",
        "get_authoritative_media_news",
        {"query": "AAPL earnings"},
        "get_authoritative_media_news failed",
    )


def test_earnings_transcripts_tool_error_is_redacted(monkeypatch):
    _assert_tool_error_redacted(
        monkeypatch,
        "_get_earnings_call_transcripts",
        "get_earnings_call_transcripts",
        {"ticker": "AAPL"},
        "get_earnings_call_transcripts failed",
    )


def test_local_market_filings_tool_error_is_redacted(monkeypatch):
    _assert_tool_error_redacted(
        monkeypatch,
        "_get_local_market_filings",
        "get_local_market_filings",
        {"ticker": "600519.SS"},
        "get_local_market_filings failed",
    )


def test_sec_filings_tool_error_is_redacted(monkeypatch):
    _assert_tool_error_redacted(
        monkeypatch,
        "_get_sec_filings",
        "get_sec_filings",
        {"ticker": "AAPL"},
        "get_sec_filings failed",
    )


def test_sec_material_events_tool_error_is_redacted(monkeypatch):
    _assert_tool_error_redacted(
        monkeypatch,
        "_get_sec_material_events",
        "get_sec_material_events",
        {"ticker": "AAPL"},
        "get_sec_material_events failed",
    )


def test_sec_company_facts_tool_error_is_redacted(monkeypatch):
    _assert_tool_error_redacted(
        monkeypatch,
        "_get_sec_company_facts_quarterly",
        "get_sec_company_facts_quarterly",
        {"ticker": "AAPL"},
        "get_sec_company_facts_quarterly failed",
    )


def test_sec_risk_factors_tool_error_is_redacted(monkeypatch):
    _assert_tool_error_redacted(
        monkeypatch,
        "_get_sec_risk_factors",
        "get_sec_risk_factors",
        {"ticker": "AAPL"},
        "get_sec_risk_factors failed",
    )


def test_screen_stocks_tool_error_is_redacted(monkeypatch):
    _assert_tool_error_redacted(
        monkeypatch,
        "_screen_stocks",
        "screen_stocks",
        {},
        "screen_stocks failed",
    )


def test_cn_market_fund_flow_tool_error_is_redacted(monkeypatch):
    _assert_tool_error_redacted(
        monkeypatch,
        "_fetch_fund_flow",
        "get_cn_market_fund_flow",
        {},
        "get_cn_market_fund_flow failed",
    )


def test_cn_market_northbound_tool_error_is_redacted(monkeypatch):
    _assert_tool_error_redacted(
        monkeypatch,
        "_fetch_northbound",
        "get_cn_market_northbound",
        {},
        "get_cn_market_northbound failed",
    )


def test_cn_limit_board_tool_error_is_redacted(monkeypatch):
    _assert_tool_error_redacted(
        monkeypatch,
        "_fetch_limit_board",
        "get_cn_limit_board",
        {},
        "get_cn_limit_board failed",
    )


def test_cn_lhb_tool_error_is_redacted(monkeypatch):
    _assert_tool_error_redacted(
        monkeypatch,
        "_fetch_lhb",
        "get_cn_lhb",
        {},
        "get_cn_lhb failed",
    )


def test_cn_concept_map_tool_error_is_redacted(monkeypatch):
    _assert_tool_error_redacted(
        monkeypatch,
        "_fetch_concept_map",
        "get_cn_concept_map",
        {},
        "get_cn_concept_map failed",
    )


def test_strategy_backtest_tool_error_is_redacted(monkeypatch):
    _assert_tool_error_redacted(
        monkeypatch,
        "_BacktestEngine",
        "run_strategy_backtest",
        {"ticker": "AAPL"},
        "run_strategy_backtest failed",
    )
