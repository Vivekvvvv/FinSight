import pandas as pd

import backend.dashboard.data_service as data_service


class _EmptyTicker:
    def history(self, **_kwargs):
        return pd.DataFrame()


def test_macro_sentiment_error_log_is_redacted(monkeypatch, caplog):
    from backend.tools import macro

    secret = "PRIVATE_SENTIMENT_ERROR_SENTINEL"

    def fail_sentiment():
        raise RuntimeError(secret)

    monkeypatch.setattr(macro, "get_market_sentiment", fail_sentiment)
    monkeypatch.setattr(macro, "get_fred_data", lambda: {})

    payload = data_service.fetch_macro_snapshot()

    assert payload["status"] == "unavailable"
    assert secret not in caplog.text
    assert "[DataService]" in caplog.text


def test_macro_fred_error_log_is_redacted(monkeypatch, caplog):
    from backend.tools import macro

    secret = "PRIVATE_FRED_ERROR_SENTINEL"

    def fail_fred():
        raise ConnectionError(secret)

    monkeypatch.setattr(macro, "get_market_sentiment", lambda: "")
    monkeypatch.setattr(macro, "get_fred_data", fail_fred)

    payload = data_service.fetch_macro_snapshot()

    assert payload["status"] == "unavailable"
    assert secret not in caplog.text
    assert "[DataService]" in caplog.text


def test_market_chart_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE_CHART_ERROR_SENTINEL"

    def fail_load(*_args, **_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(data_service, "_load_ohlcv_frame", fail_load)

    assert data_service.fetch_market_chart("AAPL") is None
    assert secret not in caplog.text
    assert "[DataService]" in caplog.text


def test_snapshot_error_log_is_redacted(monkeypatch, caplog):
    import yfinance

    secret = "PRIVATE_SNAPSHOT_ERROR_SENTINEL"

    def fail_ticker(_symbol):
        raise ConnectionError(secret)

    monkeypatch.setattr(yfinance, "Ticker", fail_ticker)

    assert data_service.fetch_snapshot("AAPL", "equity") is None
    assert secret not in caplog.text
    assert "[DataService]" in caplog.text


def test_revenue_trend_error_log_is_redacted(monkeypatch, caplog):
    import yfinance

    secret = "PRIVATE_REVENUE_PASSWORD=provider-secret"

    def fail_ticker(_symbol):
        raise RuntimeError(secret)

    monkeypatch.setattr(yfinance, "Ticker", fail_ticker)

    assert data_service.fetch_revenue_trend("AAPL") == []
    assert secret not in caplog.text
    assert "[DataService]" in caplog.text


def test_segment_mix_error_log_is_redacted(monkeypatch, caplog):
    from backend.tools import fmp

    secret = "PRIVATE_FMP_ERROR_SENTINEL"

    def fail_segments(_symbol):
        raise RuntimeError(secret)

    monkeypatch.setattr(fmp, "get_revenue_product_segmentation", fail_segments)

    assert data_service.fetch_segment_mix("AAPL") == []
    assert secret not in caplog.text
    assert "[DataService]" in caplog.text


def test_company_news_error_log_is_redacted(monkeypatch, caplog):
    from backend.tools import news

    secret = "PRIVATE_NEWS_ERROR_SENTINEL"

    def fail_company(*_args, **_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(news, "get_company_news", fail_company)
    monkeypatch.setattr(news, "get_market_news_headlines", lambda _limit: [])

    payload = data_service.fetch_news("AAPL")

    assert payload is not None
    assert secret not in caplog.text
    assert "[DataService]" in caplog.text


def test_market_news_error_log_is_redacted(monkeypatch, caplog):
    from backend.tools import news

    secret = "PRIVATE_MARKET_NEWS_ERROR_SENTINEL"

    def fail_market(*_args, **_kwargs):
        raise ConnectionError(secret)

    monkeypatch.setattr(news, "get_company_news", lambda _symbol, _limit: [])
    monkeypatch.setattr(news, "get_market_news_headlines", fail_market)

    payload = data_service.fetch_news("AAPL")

    assert payload is not None
    assert secret not in caplog.text
    assert "[DataService]" in caplog.text


def test_fetch_news_outer_error_log_is_redacted(monkeypatch, caplog):
    from backend.tools import news

    secret = "PRIVATE_RANKING_ERROR_SENTINEL"

    def fail_ranking(*_args, **_kwargs):
        raise ValueError(secret)

    monkeypatch.setattr(news, "get_company_news", lambda _symbol, _limit: [])
    monkeypatch.setattr(news, "get_market_news_headlines", lambda _limit: [])
    monkeypatch.setattr(data_service, "_rank_news_items", fail_ranking)

    payload = data_service.fetch_news("AAPL")

    assert payload == data_service._empty_news_payload()
    assert secret not in caplog.text
    assert "[DataService]" in caplog.text


def test_sector_weights_error_log_is_redacted(monkeypatch, caplog):
    from backend.tools import fmp

    secret = "PRIVATE_SECTOR_ERROR_SENTINEL"

    def fail_weights(_symbol):
        raise RuntimeError(secret)

    monkeypatch.setattr(fmp, "get_etf_sector_weights", fail_weights)

    assert data_service.fetch_sector_weights("SPY", "etf") == []
    assert secret not in caplog.text
    assert "[DataService]" in caplog.text


def test_top_constituents_error_log_is_redacted(monkeypatch, caplog):
    from backend.tools import fmp

    secret = "PRIVATE_INDEX_ERROR_SENTINEL"

    def fail_constituents(_symbol):
        raise ConnectionError(secret)

    monkeypatch.setattr(fmp, "get_index_constituents", fail_constituents)

    assert data_service.fetch_top_constituents("SPX", "index") == []
    assert secret not in caplog.text
    assert "[DataService]" in caplog.text


def test_holdings_error_log_is_redacted(monkeypatch, caplog):
    from backend.tools import fmp

    secret = "PRIVATE_HOLDINGS_PASSWORD=provider-secret"

    def fail_holdings(*_args, **_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(fmp, "get_etf_holdings", fail_holdings)

    assert data_service.fetch_holdings("SPY", "etf") == []
    assert secret not in caplog.text
    assert "[DataService]" in caplog.text


def test_cn_hk_ohlcv_error_log_is_redacted(monkeypatch, caplog):
    import yfinance
    from backend.tools import cn_hk_market, price

    secret = "PRIVATE_CN_MARKET_ERROR_SENTINEL"

    def fail_params(*_args, **_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(cn_hk_market, "kline_params_for", fail_params)
    monkeypatch.setattr(yfinance, "Ticker", lambda _symbol: _EmptyTicker())
    monkeypatch.setattr(price, "_fetch_with_stooq_history", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(price, "get_stock_historical_data", lambda *_args, **_kwargs: None)

    assert data_service._load_ohlcv_frame("600519.SS") is None
    assert secret not in caplog.text
    assert "[DataService]" in caplog.text


def test_yfinance_ohlcv_error_log_is_redacted(monkeypatch, caplog):
    import yfinance
    from backend.tools import price

    secret = "PRIVATE_YFINANCE_ERROR_SENTINEL"

    def fail_ticker(_symbol):
        raise ConnectionError(secret)

    monkeypatch.setattr(yfinance, "Ticker", fail_ticker)
    monkeypatch.setattr(price, "_fetch_with_stooq_history", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(price, "get_stock_historical_data", lambda *_args, **_kwargs: None)

    assert data_service._load_ohlcv_frame("AAPL") is None
    assert secret not in caplog.text
    assert "[DataService]" in caplog.text


def test_stooq_ohlcv_error_log_is_redacted(monkeypatch, caplog):
    import yfinance
    from backend.tools import price

    secret = "PRIVATE_STOOQ_PASSWORD=provider-secret"

    def fail_stooq(*_args, **_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(yfinance, "Ticker", lambda _symbol: _EmptyTicker())
    monkeypatch.setattr(price, "_fetch_with_stooq_history", fail_stooq)
    monkeypatch.setattr(price, "get_stock_historical_data", lambda *_args, **_kwargs: None)

    assert data_service._load_ohlcv_frame("AAPL") is None
    assert secret not in caplog.text
    assert "[DataService]" in caplog.text


def test_price_pipeline_ohlcv_error_log_is_redacted(monkeypatch, caplog):
    import yfinance
    from backend.tools import price

    secret = "PRIVATE_PRICE_PIPELINE_ERROR_SENTINEL"

    def fail_history(*_args, **_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(yfinance, "Ticker", lambda _symbol: _EmptyTicker())
    monkeypatch.setattr(price, "_fetch_with_stooq_history", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(price, "get_stock_historical_data", fail_history)

    assert data_service._load_ohlcv_frame("AAPL") is None
    assert secret not in caplog.text
    assert "[DataService]" in caplog.text


def test_finnhub_request_error_log_is_redacted(monkeypatch, caplog):
    from backend.tools import env, http

    secret = "PRIVATE_FINNHUB_ERROR_SENTINEL"

    def fail_request(*_args, **_kwargs):
        raise ConnectionError(secret)

    monkeypatch.setattr(env, "FINNHUB_API_KEY", "configured-test-key")
    monkeypatch.setattr(http, "_http_get", fail_request)

    assert data_service._finnhub_request("stock/profile2") is None
    assert secret not in caplog.text
    assert "[DataService]" in caplog.text


def test_cn_hk_valuation_error_log_is_redacted(monkeypatch, caplog):
    from backend.tools import cn_hk_market

    secret = "PRIVATE_VALUATION_ERROR_SENTINEL"

    def fail_metrics(_symbol):
        raise RuntimeError(secret)

    monkeypatch.setattr(cn_hk_market, "fetch_cn_hk_quote_metrics", fail_metrics)

    assert data_service._fetch_valuation_from_cn_hk_market("600519.SS") is None
    assert secret not in caplog.text
    assert "[DataService]" in caplog.text


def test_sec_companyfacts_error_log_is_redacted(monkeypatch, caplog):
    from backend.tools import sec

    secret = "PRIVATE_SEC_ERROR_SENTINEL"

    def fail_companyfacts(*_args, **_kwargs):
        raise ConnectionError(secret)

    monkeypatch.setattr(sec, "get_sec_company_facts_quarterly", fail_companyfacts)

    assert data_service._fetch_financial_statements_from_sec_companyfacts("AAPL") is None
    assert secret not in caplog.text
    assert "[DataService]" in caplog.text


def test_cn_hk_financials_error_log_is_redacted(monkeypatch, caplog):
    from backend.tools import cn_hk_market

    secret = "PRIVATE_FINANCIALS_PASSWORD=provider-secret"

    def fail_financials(*_args, **_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(cn_hk_market, "fetch_cn_hk_financial_statements", fail_financials)

    assert data_service._fetch_financial_statements_from_cn_hk_market("600519.SS") is None
    assert secret not in caplog.text
    assert "[DataService]" in caplog.text


def test_fetch_valuation_error_log_is_redacted(monkeypatch, caplog):
    import yfinance

    secret = "PRIVATE_YF_VALUATION_ERROR_SENTINEL"

    def fail_ticker(_symbol):
        raise RuntimeError(secret)

    monkeypatch.setattr(yfinance, "Ticker", fail_ticker)
    monkeypatch.setattr(data_service, "_fetch_valuation_from_finnhub", lambda _symbol: None)

    assert data_service.fetch_valuation("AAPL") is None
    assert secret not in caplog.text
    assert "[DataService]" in caplog.text


def test_fetch_financial_statements_error_log_is_redacted(monkeypatch, caplog):
    import yfinance

    secret = "PRIVATE_YF_FINANCIALS_ERROR_SENTINEL"

    def fail_ticker(_symbol):
        raise ConnectionError(secret)

    monkeypatch.setattr(yfinance, "Ticker", fail_ticker)
    monkeypatch.setattr(
        data_service,
        "_fetch_financial_statements_from_sec_companyfacts",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        data_service,
        "_fetch_financial_statements_from_finnhub",
        lambda *_args, **_kwargs: None,
    )

    assert data_service.fetch_financial_statements("AAPL") is None
    assert secret not in caplog.text
    assert "[DataService]" in caplog.text


def test_technical_indicators_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE_TECHNICAL_ERROR_SENTINEL"

    def fail_load(*_args, **_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(data_service, "_load_ohlcv_frame", fail_load)

    assert data_service.fetch_technical_indicators("AAPL") is None
    assert secret not in caplog.text
    assert "[DataService]" in caplog.text


def test_indicator_series_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE_INDICATOR_PASSWORD=provider-secret"

    def fail_load(*_args, **_kwargs):
        raise ConnectionError(secret)

    monkeypatch.setattr(data_service, "_load_ohlcv_frame", fail_load)

    assert data_service.fetch_indicator_series("AAPL") is None
    assert secret not in caplog.text
    assert "[DataService]" in caplog.text


def test_earnings_history_error_log_is_redacted(monkeypatch, caplog):
    import yfinance

    secret = "PRIVATE_EARNINGS_ERROR_SENTINEL"

    def fail_ticker(_symbol):
        raise RuntimeError(secret)

    monkeypatch.setattr(yfinance, "Ticker", fail_ticker)

    assert data_service.fetch_earnings_history("AAPL") is None
    assert secret not in caplog.text
    assert "[DataService]" in caplog.text


def test_analyst_targets_error_log_is_redacted(monkeypatch, caplog):
    import yfinance

    secret = "PRIVATE_ANALYST_ERROR_SENTINEL"

    def fail_ticker(_symbol):
        raise ConnectionError(secret)

    monkeypatch.setattr(yfinance, "Ticker", fail_ticker)

    assert data_service.fetch_analyst_targets("AAPL") is None
    assert secret not in caplog.text
    assert "[DataService]" in caplog.text


def test_recommendations_error_log_is_redacted(monkeypatch, caplog):
    import yfinance

    secret = "PRIVATE_RECOMMENDATIONS_PASSWORD=provider-secret"

    def fail_ticker(_symbol):
        raise RuntimeError(secret)

    monkeypatch.setattr(yfinance, "Ticker", fail_ticker)

    assert data_service.fetch_recommendations("AAPL") is None
    assert secret not in caplog.text
    assert "[DataService]" in caplog.text
