# -*- coding: utf-8 -*-
import pytest

from backend.graph.nodes.alert_extractor import alert_extractor


def test_alert_extractor_prefers_subject_ticker_over_active_symbol():
    state = {
        "query": "涨到 12 元提醒我",
        "subject": {"tickers": ["000001.SZ"]},
        "ui_context": {"active_symbol": "AAPL"},
    }
    result = alert_extractor(state)
    assert result["alert_valid"] is True
    params = result["alert_params"]
    assert params["ticker"] == "000001.SZ"
    assert params["alert_mode"] == "price_target"
    assert params["price_target"] == 12.0


def test_alert_extractor_falls_back_to_active_symbol():
    state = {
        "query": "跌到 8 元提醒我",
        "subject": {"tickers": []},
        "ui_context": {"active_symbol": "000001.sz"},
    }
    result = alert_extractor(state)
    assert result["alert_valid"] is True
    params = result["alert_params"]
    assert params["ticker"] == "000001.SZ"
    assert params["direction"] == "below"


def test_alert_extractor_missing_ticker_returns_clarify():
    state = {
        "query": "涨到 20 元提醒我",
        "subject": {"tickers": []},
        "ui_context": {},
    }
    result = alert_extractor(state)
    assert result["alert_valid"] is False
    clarify = result.get("clarify") or {}
    assert clarify.get("needed") is True


def test_alert_extractor_pct_mode():
    state = {
        "query": "AAPL 涨跌超过 3% 提醒我",
        "subject": {"tickers": ["AAPL"]},
        "ui_context": {},
    }
    result = alert_extractor(state)
    assert result["alert_valid"] is True
    params = result["alert_params"]
    assert params["alert_mode"] == "price_change_pct"
    assert params["price_threshold"] == 3.0


@pytest.mark.parametrize("threshold,unit", [
    (5.0, "%"), (12.5, "%"), (12.5, " percent"),
    (25.0, "pct"), (12.5, " 个点"), (12.5, " PERCENT"),
])
def test_percentage_after_over_is_not_interpreted_as_target_price(threshold, unit):
    result = alert_extractor({
        "query": f"Notify me if AAPL moves over {threshold}{unit}",
        "subject": {"tickers": ["AAPL"]},
    })

    assert result["alert_valid"] is True
    assert result["alert_params"]["alert_mode"] == "price_change_pct"
    assert result["alert_params"]["price_threshold"] == threshold
    assert result["alert_params"]["price_target"] is None


@pytest.mark.parametrize("query", [
    "Notify me when AAPL goes over 125.5 USD",
    "Notify me when AAPL goes over 125.5 USD or moves over 12.5%",
    "Notify me when AAPL reaches 125.5. Thanks.",
    "AAPL 涨到 125.5 元提醒我",
])
def test_absolute_prices_keep_target_mode(query):
    result = alert_extractor({"query": query, "subject": {"tickers": ["AAPL"]}})

    assert result["alert_valid"] is True
    assert result["alert_params"]["alert_mode"] == "price_target"
    assert result["alert_params"]["price_target"] == 125.5


@pytest.mark.parametrize("query", [
    "Alert me when AAPL hits 12.5%",
    "AAPL 涨到 12.5% 提醒我",
])
def test_percentage_with_unrecognized_trigger_requests_clarification(query):
    result = alert_extractor({"query": query, "subject": {"tickers": ["AAPL"]}})

    assert result["alert_valid"] is False
    assert result["clarify"]["needed"] is True
    assert result["alert_params"]["price_target"] is None
