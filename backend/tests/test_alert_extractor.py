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


@pytest.mark.parametrize("query", [
    "不要在 AAPL 涨到 220 美元时提醒我",
    "别帮我设置 AAPL 涨到 220 的提醒",
    "我不需要 AAPL 涨跌超过 3% 的提醒",
    "不用在 AAPL 跌到 80 时通知我",
    "无需订阅 AAPL 涨到 220 的预警",
    "勿在 AAPL 涨到 220 时提醒我",
    "Don't notify me when AAPL hits 220",
    "Don’t notify me when AAPL hits 220",
    "Dont notify me when AAPL hits 220",
    "Do not create an alert when AAPL goes above 220",
    "Never alert me when AAPL drops below 80",
    "No need to set an alert when AAPL moves 5%",
])
def test_declined_alert_creation_cannot_proceed(query):
    result = alert_extractor({"query": query, "subject": {"tickers": ["AAPL"]}})

    assert result["alert_valid"] is False
    assert result["skip_session_context"] is True
    assert result["alert_params"]["alert_mode"] is None
    assert "未创建" in result["artifacts"]["draft_markdown"]


@pytest.mark.parametrize("query", [
    "不要忘记在 AAPL 涨到 220 时提醒我",
    "别忘了 AAPL 跌到 80 时提醒我",
    "Don't forget to notify me when AAPL hits 220",
    "Don’t forget to notify me when AAPL hits 220",
    "Don't cancel existing alerts; notify me when AAPL rises above 220",
    "不要取消现有提醒，AAPL 涨到 220 时提醒我",
    "不要买入 AAPL，涨到 220 时提醒我",
    "AAPL 涨到 220 时特别提醒我",
    "分别为 AAPL 设置涨到 220 的提醒",
])
def test_affirmative_alert_request_with_unrelated_negation_still_proceeds(query):
    result = alert_extractor({"query": query, "subject": {"tickers": ["AAPL"]}})

    assert result["alert_valid"] is True
    assert result["alert_params"]["alert_mode"] == "price_target"
