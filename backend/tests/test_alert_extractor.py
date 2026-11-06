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


def test_multiple_alert_tickers_require_clarification():
    result = alert_extractor({
        "query": "AAPL 和 TSLA 涨到 220 时提醒我",
        "subject": {"tickers": ["AAPL", "TSLA"]},
    })

    assert result["alert_valid"] is False
    assert result["skip_session_context"] is True
    assert result["alert_params"]["alert_mode"] is None
    assert result["clarify"]["reason"] == "alert_multiple_tickers"


def test_repeated_same_alert_ticker_still_proceeds():
    result = alert_extractor({
        "query": "AAPL 涨到 220 时提醒我",
        "subject": {"tickers": ["AAPL", " aapl "]},
    })

    assert result["alert_valid"] is True
    assert result["alert_params"]["ticker"] == "AAPL"


def test_currency_unit_in_target_does_not_count_as_alert_ticker():
    result = alert_extractor({
        "query": "Notify me at 220 USD for AAPL",
        "subject": {"tickers": ["USD", "AAPL"]},
    })

    assert result["alert_valid"] is True
    assert result["alert_params"]["ticker"] == "AAPL"


def test_usd_ticker_outside_price_condition_still_counts():
    result = alert_extractor({
        "query": "USD and TSLA go above 220 USD; alert me",
        "subject": {"tickers": ["USD", "TSLA"]},
    })

    assert result["alert_valid"] is False
    assert result["clarify"]["reason"] == "alert_multiple_tickers"


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


@pytest.mark.parametrize("query", [
    "Notify me about AAPL turnover 220 USD",
    "Notify me about AAPL format220",
    "Notify me about AAPL rollover 5%",
    "Notify me about AAPL BACKUP5%",
])
def test_embedded_english_trigger_requires_clarification(query):
    result = alert_extractor({"query": query, "subject": {"tickers": ["AAPL"]}})

    assert result["alert_valid"] is False
    assert result["alert_params"]["alert_mode"] is None
    assert result["alert_params"]["price_target"] is None
    assert result["alert_params"]["price_threshold"] is None
    assert result["clarify"]["needed"] is True


@pytest.mark.parametrize("query,mode,field,expected", [
    ("AAPL 价格above220美元时提醒我", "price_target", "price_target", 220.0),
    ("AAPL 涨幅over3%时提醒我", "price_change_pct", "price_threshold", 3.0),
])
def test_english_trigger_after_cjk_accepts_adjacent_number(query, mode, field, expected):
    result = alert_extractor({"query": query, "subject": {"tickers": ["AAPL"]}})

    assert result["alert_valid"] is True
    assert result["alert_params"]["alert_mode"] == mode
    assert result["alert_params"][field] == expected


@pytest.mark.parametrize("query,expected_direction", [
    ("Notify me when AAPL goes above 220 so I can understand the move", "above"),
    ("Notify me when AAPL hits 80; give me an overview", None),
    ("Notify me when AAPL hits 220; include the underlying rationale", None),
    ("Notify me when AAPL goes over 1,000; I understand the risks", "above"),
])
def test_english_prose_does_not_supply_alert_direction(query, expected_direction):
    result = alert_extractor({"query": query, "subject": {"tickers": ["AAPL"]}})

    assert result["alert_valid"] is True
    assert result["alert_params"]["alert_mode"] == "price_target"
    assert result["alert_params"]["direction"] == expected_direction


@pytest.mark.parametrize("query,expected_direction", [
    ("Notify me when AAPL goes above 220; I am under my budget", "above"),
    ("Notify me when AAPL rises to 80; costs are under control", "above"),
    ("Notify me when AAPL hits 80; show performance over time", None),
    ("Notify me when AAPL hits 220; costs are under control", None),
    ("AAPL 涨到 220 时提醒我；附上低于市场预期的原因", "above"),
    ("AAPL 到 80 元提醒我；附上高于市场预期的消息", None),
])
def test_background_direction_words_do_not_change_price_condition(query, expected_direction):
    result = alert_extractor({"query": query, "subject": {"tickers": ["AAPL"]}})

    assert result["alert_valid"] is True
    assert result["alert_params"]["direction"] == expected_direction


@pytest.mark.parametrize("word,price,expected_direction", [
    ("below", 80, "below"),
    ("under", 80, "below"),
    ("above", 220, "above"),
    ("over", 220, "above"),
    ("BELOW", 80, "below"),
    ("OVER", 220, "above"),
])
def test_english_direction_accepts_adjacent_price(word, price, expected_direction):
    result = alert_extractor({
        "query": f"Notify me when AAPL goes {word}{price}",
        "subject": {"tickers": ["AAPL"]},
    })

    assert result["alert_valid"] is True
    assert result["alert_params"]["price_target"] == price
    assert result["alert_params"]["direction"] == expected_direction


@pytest.mark.parametrize("movement,price,expected_direction", [
    ("drops", 220, "below"),
    ("falls", 220, "below"),
    ("dips", 220, "below"),
    ("rises", 80, "above"),
    ("climbs", 80, "above"),
    ("FALLS", 220, "below"),
    ("CLIMBS", 80, "above"),
])
def test_directional_movement_to_price_is_explicit(movement, price, expected_direction):
    result = alert_extractor({
        "query": f"Notify me when AAPL {movement} to{price} USD",
        "subject": {"tickers": ["AAPL"]},
    })

    assert result["alert_valid"] is True
    assert result["alert_params"]["price_target"] == price
    assert result["alert_params"]["direction"] == expected_direction


@pytest.mark.parametrize("movement,price,expected_direction", [
    ("跌至", "220", "below"),
    ("下跌至", "220", "below"),
    ("涨至", "80", "above"),
    ("上涨至", "80", "above"),
    ("跌至", "1,000.5", "below"),
    ("涨至", "1,000.5", "above"),
    ("跌破", "220", "below"),
    ("低于", "220", "below"),
    ("小于", "220", "below"),
    ("突破", "80", "above"),
    ("高于", "80", "above"),
    ("大于", "80", "above"),
])
def test_chinese_movement_to_price_keeps_explicit_direction(movement, price, expected_direction):
    result = alert_extractor({
        "query": f"AAPL {movement}{price}美元时提醒我",
        "subject": {"tickers": ["AAPL"]},
    })

    assert result["alert_valid"] is True
    assert result["alert_params"]["price_target"] == float(price.replace(",", ""))
    assert result["alert_params"]["direction"] == expected_direction


@pytest.mark.parametrize("query,price,expected_direction", [
    ("Notify me when AAPL goes above $220", 220.0, "above"),
    ("Notify me when AAPL drops to $12,500.75", 12500.75, "below"),
    ("Notify me when AAPL hits $220", 220.0, None),
    ("AAPL 涨到$220时提醒我", 220.0, "above"),
])
def test_dollar_prefixed_target_keeps_price_and_direction(query, price, expected_direction):
    result = alert_extractor({"query": query, "subject": {"tickers": ["AAPL"]}})

    assert result["alert_valid"] is True
    assert result["alert_params"]["alert_mode"] == "price_target"
    assert result["alert_params"]["price_target"] == price
    assert result["alert_params"]["direction"] == expected_direction


@pytest.mark.parametrize("query", [
    "Notify me when AAPL goes to 90",
    "Notify me when AAPL hits 220; risk rises to a higher level",
    "Notify me when AAPL hits 220; interest rates fall to 3%",
    "Notify me when AAPL hits 220; interest rates rise to 3%",
])
def test_generic_or_unrelated_to_phrase_does_not_supply_direction(query):
    result = alert_extractor({"query": query, "subject": {"tickers": ["AAPL"]}})

    assert result["alert_valid"] is True
    assert result["alert_params"]["direction"] is None


@pytest.mark.parametrize("threshold,unit", [
    (5.0, "%"), (12.5, "%"), (12.5, " percent"),
    (25.0, "pct"), (12.5, " 个点"), (12.5, " PERCENT"),
    (3.0, "％"), (12.5, " per cent"), (12.5, " PER CENT"),
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
    "AAPL 涨到 220 或跌到 180 时提醒我",
    "Notify me when AAPL goes above 220 or below 180",
    "AAPL 涨到 220 或涨到 230 时提醒我",
    "AAPL 涨跌超过 3% 或涨跌超过 5% 时提醒我",
    "Notify me if AAPL moves over 3% or falls 5%",
    "Notify me when AAPL goes above 220 or moves over 3% or falls 5%",
    "AAPL 涨到 220 或跌到 220 时提醒我",
    "Notify me when AAPL goes above 220 or below 220",
    "Notify me when AAPL goes over 1,000 or under 1000.0",
    "Notify me when AAPL rises to 220 or falls to 220",
    "AAPL 涨至 220 或跌至 220 时提醒我",
    "AAPL 涨到 220 或跌至 220 时提醒我",
    "Notify me when AAPL goes above $220 or below 180",
    "Notify me when AAPL goes above 220 or below $180",
    "Notify me when AAPL goes above $220 or below $220",
    "AAPL 低于220元或涨到220元时提醒我",
    "AAPL 突破220元或跌破220元时提醒我",
])
def test_conflicting_thresholds_require_clarification(query):
    result = alert_extractor({"query": query, "subject": {"tickers": ["AAPL"]}})

    assert result["alert_valid"] is False
    assert result["skip_session_context"] is True
    assert result["alert_params"]["alert_mode"] is None
    assert result["clarify"]["needed"] is True
    assert result["clarify"]["reason"] == "alert_conflicting_thresholds"
    assert "一次" in result["artifacts"]["draft_markdown"]


@pytest.mark.parametrize("query,mode,field,expected", [
    ("Notify me when AAPL goes above 1,000 or above 1000.0", "price_target", "price_target", 1000.0),
    ("AAPL 涨到 220 或涨到 220.0 时提醒我", "price_target", "price_target", 220.0),
    ("Notify me if AAPL moves over 3% or rises 3.0 percent", "price_change_pct", "price_threshold", 3.0),
    ("Notify me when AAPL hits 220 or goes above 220", "price_target", "price_target", 220.0),
    ("Notify me when AAPL goes below 220 or hits 220", "price_target", "price_target", 220.0),
])
def test_repeated_equivalent_thresholds_are_not_conflicting(query, mode, field, expected):
    result = alert_extractor({"query": query, "subject": {"tickers": ["AAPL"]}})

    assert result["alert_valid"] is True
    assert result["alert_params"]["alert_mode"] == mode
    assert result["alert_params"][field] == expected


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


@pytest.mark.parametrize("query,expected_price", [
    ("AAPL 涨到 1,000 美元时提醒我", 1000.0),
    ("AAPL 跌到 12,500.75 元时提醒我", 12500.75),
    ("Notify me when AAPL goes above 1,234,567.89 USD", 1234567.89),
    ("Notify me when AAPL reaches 1,000.50. Thanks.", 1000.5),
])
def test_grouped_target_prices_are_not_truncated(query, expected_price):
    result = alert_extractor({"query": query, "subject": {"tickers": ["AAPL"]}})

    assert result["alert_valid"] is True
    assert result["alert_params"]["alert_mode"] == "price_target"
    assert result["alert_params"]["price_target"] == expected_price


@pytest.mark.parametrize("query", [
    "AAPL 涨到 1,00 元时提醒我",
    "Notify me when AAPL goes above 12,34,567 USD",
    "AAPL 涨到 1234,567 美元时提醒我",
    "Notify me when AAPL goes above 1,0000 USD",
    "AAPL 涨到 1，000 美元时提醒我",
    "Notify me when AAPL hits 1,000%",
    "Notify me when AAPL goes above $1,00",
    "Notify me when AAPL hits $12.5%",
])
def test_invalid_or_percentage_grouped_price_requests_clarification(query):
    result = alert_extractor({"query": query, "subject": {"tickers": ["AAPL"]}})

    assert result["alert_valid"] is False
    assert result["alert_params"]["price_target"] is None
    assert result["clarify"]["needed"] is True


@pytest.mark.parametrize("query", [
    "Notify me when AAPL goes above 1e3 USD",
    "Notify me when AAPL is at 2.2e2 USD",
    "Notify me when AAPL goes below 1E+3 USD",
    "AAPL 涨到 2e-3 元时提醒我",
    "AAPL 涨到 1,000e3 元时提醒我",
    "Notify me when AAPL goes above $1e3",
])
def test_scientific_target_price_requires_clarification(query):
    result = alert_extractor({"query": query, "subject": {"tickers": ["AAPL"]}})

    assert result["alert_valid"] is False
    assert result["alert_params"]["price_target"] is None
    assert result["clarify"]["needed"] is True


@pytest.mark.parametrize("query", [
    "AAPL 涨到 1万元时提醒我",
    "AAPL 涨到 1.5 千元时提醒我",
    "Notify me when AAPL goes above $2k",
    "Notify me when AAPL goes above 1.5M USD",
    "Notify me when AAPL goes above 2 thousand dollars",
])
def test_scaled_target_price_requires_plain_amount(query):
    result = alert_extractor({"query": query, "subject": {"tickers": ["AAPL"]}})

    assert result["alert_valid"] is False
    assert result["alert_params"]["price_target"] is None
    assert result["clarify"]["needed"] is True


@pytest.mark.parametrize("query", [
    "Notify me when AAPL goes above 220-230",
    "AAPL 涨到 220 至 230 元时提醒我",
    "AAPL 涨到 1/2 元时提醒我",
    "Notify me when AAPL goes above 220~230",
    "Notify me when AAPL goes above 220 to 230",
])
def test_range_or_fraction_target_requires_clarification(query):
    result = alert_extractor({"query": query, "subject": {"tickers": ["AAPL"]}})

    assert result["alert_valid"] is False
    assert result["clarify"]["needed"] is True


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
    "I do not want an alert when AAPL goes above 220",
    "I don't want any alerts when AAPL goes above 220",
    "I don’t need price alerts if AAPL moves over 3%",
    "I do not need a reminder when AAPL goes below 80",
    "No need for an alert when AAPL goes above 220",
    "No need for notifications when AAPL moves over 3%",
    "不要在 AAPL 涨到 1,000 美元时提醒我",
    "不要在 AAPL 涨到 12,500.75 美元时提醒我",
    "Do not create an AAPL above 125.5 alert",
    "Don't add an AAPL above 1,000.5 alert",
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
    "I don't want to buy AAPL; alert me when it goes above 220",
    "I do not need a report; notify me when AAPL goes above 220",
    "No need for a report; alert me when AAPL goes above 220",
])
def test_affirmative_alert_request_with_unrelated_negation_still_proceeds(query):
    result = alert_extractor({"query": query, "subject": {"tickers": ["AAPL"]}})

    assert result["alert_valid"] is True
    assert result["alert_params"]["alert_mode"] == "price_target"


@pytest.mark.parametrize("query", [
    "取消 AAPL 涨到 220 的提醒",
    "取消 AAPL 涨到 125.5 的提醒",
    "取消 AAPL 涨到 1,000 美元的提醒",
    "撤销 AAPL 涨跌超过 3% 的预警",
    "停用 AAPL 跌到 80 的提醒",
    "关闭 AAPL 涨到 220 的通知",
    "删除 AAPL 涨到 220 的订阅",
    "停止在 AAPL 跌到 80 时提醒我",
    "Cancel my AAPL alert when it goes above 220",
    "Disable AAPL notifications when it reaches 220",
    "Stop sending AAPL alerts when it falls below 80",
    "Unsubscribe AAPL alerts when it goes above 220",
    "不要取消旧提醒但取消 AAPL 涨到 220 的提醒",
    "Turn off AAPL alerts when it goes above 220",
    "Switch off AAPL notifications when it falls below 80",
    "Turn off the AAPL above $1,000.5 reminder",
])
def test_cancellation_request_cannot_create_alert(query):
    result = alert_extractor({"query": query, "subject": {"tickers": ["AAPL"]}})

    assert result["alert_valid"] is False
    assert result["skip_session_context"] is True
    assert result["alert_params"]["alert_mode"] is None
    assert "提醒设置" in result["artifacts"]["draft_markdown"]


@pytest.mark.parametrize("query", [
    "不要 取消现有提醒，AAPL 涨到 220 时提醒我",
    "先别停用现有提醒，AAPL 跌到 80 时提醒我",
    "Don't    cancel existing alerts; notify me when AAPL goes above 220",
    "Don't ever cancel existing alerts; notify me when AAPL goes above 220",
    "No need to disable existing alerts; notify me when AAPL goes above 220",
    "Never unsubscribe existing alerts; notify me when AAPL goes above 220",
    "Cancel my buy order; notify me when AAPL goes above 220",
    "Cancel my buy order. Set an alert when AAPL goes above 220",
    "取消 AAPL 订单，涨到 220 时提醒我",
    "Don't turn off existing alerts; notify me when AAPL goes above 220",
    "Do not switch off existing alerts; notify me when AAPL goes above 220",
    "Turn off the lights; notify me when AAPL goes above 220",
])
def test_negated_or_unrelated_cancellation_keeps_affirmative_alert_request(query):
    result = alert_extractor({"query": query, "subject": {"tickers": ["AAPL"]}})

    assert result["alert_valid"] is True
    assert result["alert_params"]["alert_mode"] == "price_target"
