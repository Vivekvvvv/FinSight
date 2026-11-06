# -*- coding: utf-8 -*-
import pytest

from backend.graph.nodes.parse_operation import parse_operation


def test_parse_operation_detects_alert_set_cn_target():
    result = parse_operation(
        {
            "query": "平安银行涨到12元提醒我",
            "subject": {"subject_type": "company", "tickers": ["000001.SZ"]},
        }
    )
    assert result["operation"]["name"] == "alert_set"
    decision = (result.get("trace") or {}).get("operation_decision") or {}
    assert decision.get("guardrail_a_hit") == "alert_set"


def test_parse_operation_detects_alert_set_en_phrase():
    result = parse_operation(
        {
            "query": "notify me when it reaches 220",
            "subject": {"subject_type": "company", "tickers": ["AAPL"]},
        }
    )
    assert result["operation"]["name"] == "alert_set"


def test_parse_operation_alert_priority_over_price_keyword():
    result = parse_operation(
        {
            "query": "AAPL 涨到 220 的时候提醒我，并告诉我当前 price",
            "subject": {"subject_type": "company", "tickers": ["AAPL"]},
        }
    )
    assert result["operation"]["name"] == "alert_set"


@pytest.mark.parametrize("query", [
    "Set a reminder when AAPL drops below 80",
    "Create a notification when AAPL goes above 220",
    "Turn AAPL reminders off when it falls below 80",
    "Remove my reminder when AAPL goes above 220",
])
def test_reminder_and_notification_nouns_route_to_alert_flow(query):
    result = parse_operation({
        "query": query,
        "subject": {"subject_type": "company", "tickers": ["AAPL"]},
    })

    assert result["operation"]["name"] == "alert_set"
    assert result["trace"]["operation_decision"]["guardrail_a_hit"] == "alert_set"


@pytest.mark.parametrize("query", [
    "AAPL reminder_count220",
    "AAPL notifications_cache220",
])
def test_embedded_reminder_and_notification_names_do_not_route_to_alert(query):
    result = parse_operation({
        "query": query,
        "subject": {"subject_type": "company", "tickers": ["AAPL"]},
    })

    assert result["operation"]["name"] == "qa"
