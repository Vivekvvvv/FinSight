# -*- coding: utf-8 -*-
"""测试 next_actions 推荐引擎"""
from backend.services.next_actions import generate_next_actions


def test_alert_actions_normalize_optional_tickers_and_use_safe_fallback_routes():
    for ticker in ([], {}, True, 123, "  "):
        actions = generate_next_actions(None, [], [], [{"id": "a", "ticker": ticker}])
        item = next(item for item in actions if item["type"] == "check_alert")
        assert item["target_route"] == "/alerts"
        assert item["related_symbol"] is None
    item = next(item for item in generate_next_actions(None, [], [], [{"id": "a", "ticker": " aapl "}])
                if item["type"] == "check_alert")
    assert item["target_route"] == "/dashboard/AAPL"


def test_refresh_actions_ignore_identifierless_reports_before_limiting():
    rows = [{"report_id": value} for value in (None, "", " ", [], True, 123)]
    rows.append({"report_id": "valid"})
    actions = generate_next_actions(None, [], rows, [])
    assert [item["id"] for item in actions if item["type"] == "refresh_report"] == ["refresh_valid"]


def test_watchlist_reason_values_cannot_escape_as_nontext_actions():
    for reason in ([], {"bad": True}, 123, "  "):
        actions = generate_next_actions(None, [{"ticker": "AAPL", "priority": 5,
                                               "research_status": "reviewing", "watch_reason": reason}], [], [])
        selected = [item for item in actions if item["type"] in {"focus_watchlist", "research_review"}]
        assert len(selected) == 2
        assert all(isinstance(item["reason"], str) and item["reason"].strip() for item in selected)


def test_alert_reason_is_always_nonempty_text():
    for title in ([], {"bad": True}, 123, "  "):
        actions = generate_next_actions(None, [], [], [{"id": "a1", "ticker": "AAPL", "title": title}])
        item = next(item for item in actions if item["type"] == "check_alert")
        assert isinstance(item["reason"], str) and item["reason"].strip()
        assert item["reason"] == "触发价格或新闻提醒"


def test_duplicate_recommendations_do_not_hide_other_instruments():
    rows = [{"ticker": "AAPL", "priority": 5}, {"ticker": " aapl ", "priority": 5},
            {"ticker": "MSFT", "priority": 4}]
    actions = generate_next_actions(None, rows, [], [])
    assert [item["related_symbol"] for item in actions if item["type"] == "focus_watchlist"] == ["AAPL", "MSFT"]


def test_failed_position_rows_cannot_create_loss_actions():
    rows = [{"ticker": "BAD", "cost_basis": 1000, "unrealized_pnl": -200, **failure}
            for failure in ({"success": False}, {"error": "bad"}, {"status": " Failed "})]
    rows.append({"ticker": "AAPL", "cost_basis": 1000, "unrealized_pnl": -200})
    actions = generate_next_actions({"positions": rows}, [], [], [])
    assert [item["related_symbol"] for item in actions if item["type"] == "risk_check"] == ["AAPL"]


def test_failed_watchlist_items_do_not_create_focus_or_research_actions():
    rows = [{"ticker": "BAD", "priority": 5, "research_status": "reviewing", **failure}
            for failure in ({"success": False}, {"error": "bad"}, {"status": " Failed "})]
    rows.append({"ticker": "AAPL", "priority": 5})
    actions = generate_next_actions(None, rows, [], [])
    assert [item["related_symbol"] for item in actions if item["type"] == "focus_watchlist"] == ["AAPL"]
    assert all(item["type"] != "research_review" for item in actions)


def test_failed_alerts_do_not_displace_valid_alert_actions():
    rows = [{"id": "bad", "ticker": "AAPL", **failure} for failure in
            ({"success": False}, {"error": "bad"}, {"status": " Failed "})]
    rows.append({"id": "valid", "ticker": "AAPL"})
    actions = generate_next_actions(None, [], [], rows)
    assert [item["id"] for item in actions if item["type"] == "check_alert"] == ["alert_valid"]


def test_failed_reports_cannot_displace_actionable_refresh_recommendations():
    rows = [{"report_id": "bad", **failure} for failure in
            ({"success": False}, {"error": "bad"}, {"status": " Failed "})]
    rows.append({"report_id": "valid", "ticker": "AAPL"})
    actions = generate_next_actions(None, [], rows, [])
    assert [item["id"] for item in actions if item["type"] == "refresh_report"] == ["refresh_valid"]


def test_risk_actions_require_normalized_string_position_tickers():
    positions = [{"ticker": value, "cost_basis": 1000, "unrealized_pnl": -200}
                 for value in (None, "", " ", [], True, 123)]
    positions.append({"ticker": " aapl ", "cost_basis": 1000, "unrealized_pnl": -200})
    actions = generate_next_actions({"positions": positions}, [], [], [])
    risks = [item for item in actions if item["type"] == "risk_check"]
    assert [item["related_symbol"] for item in risks] == ["AAPL"]
    assert risks[0]["target_route"] == "/dashboard/AAPL"
    assert positions[-1]["ticker"] == " aapl "


def test_action_watchlist_requires_normalized_string_tickers():
    rows = [{"ticker": value, "priority": 5, "research_status": "reviewing"}
            for value in (None, "", " ", [], True, 123)]
    rows.append({"ticker": " aapl ", "priority": 5, "research_status": "reviewing"})
    actions = generate_next_actions(None, rows, [], [])
    focus = [item for item in actions if item["type"] in {"focus_watchlist", "research_review"}]
    assert [item["related_symbol"] for item in focus] == ["AAPL", "AAPL"]
    assert rows[-1]["ticker"] == " aapl "


def test_loss_amount_normalization_keeps_valid_actions():
    positions = [
        {"ticker": "AAPL", "unrealized_pnl": "-110", "cost_basis": "1000"},
        {"ticker": "BAD", "unrealized_pnl": "-inf", "cost_basis": 1000},
        {"ticker": "BOOL", "unrealized_pnl": -1, "cost_basis": True},
    ]
    actions = generate_next_actions({"positions": positions}, [], [], [])
    risks = [action for action in actions if action["type"] == "risk_check"]
    assert [action["related_symbol"] for action in risks] == ["AAPL"]
    assert risks[0]["severity"] == "high"


def test_overflowing_loss_percentage_does_not_escape_into_risk_text():
    actions = generate_next_actions({"positions": [
        {"ticker": "OVERFLOW", "unrealized_pnl": -1e308, "cost_basis": 1e-308},
        {"ticker": "TEXT_OVERFLOW", "unrealized_pnl": -1e307, "cost_basis": 1},
        {"ticker": "AAPL", "unrealized_pnl": -110, "cost_basis": 1000},
    ]}, [], [], [])

    risks = [action for action in actions if action["type"] == "risk_check"]
    assert [action["related_symbol"] for action in risks] == ["AAPL"]
    assert risks[0]["reason"] == "持仓亏损 -11.0%"


def test_malformed_recommendation_rows_do_not_remove_healthy_actions():
    portfolio = {"positions": [None, {"ticker": "AAPL", "cost_basis": 1000, "unrealized_pnl": -110}]}
    actions = generate_next_actions(
        portfolio,
        [None, "bad", {"ticker": "AAPL", "priority": 5}],
        [None, {"report_id": "r1", "ticker": "AAPL"}],
        [None, {"id": "a1", "ticker": "AAPL"}],
    )
    assert {action["type"] for action in actions} == {"risk_check", "focus_watchlist", "refresh_report", "check_alert"}
    assert portfolio["positions"][0] is None


def test_malformed_alert_severity_uses_valid_default():
    for raw, expected in (({}, "medium"), ([], "medium"), (None, "medium"), (" HIGH ", "high"), ("invalid", "medium")):
        actions = generate_next_actions(None, [], [], [{"ticker": "AAPL", "id": "a1", "severity": raw}])
        alert = next(action for action in actions if action["type"] == "check_alert")
        assert alert["severity"] == expected


def test_malformed_review_reasons_preserve_valid_reason_text():
    for raw, expected in ((["数据过期", None, {}], "数据过期"), ("手动复查", "手动复查"), (None, "数据可能过期")):
        actions = generate_next_actions(None, [], [{"report_id": "r1", "_review_reasons": raw}], [])
        action = next(action for action in actions if action["type"] == "refresh_report")
        assert action["reason"] == expected


def test_highest_priority_before_limit_is_not_hidden_by_earlier_items():
    watchlist = [{"ticker": "FIRST", "priority": 4}, {"ticker": "SECOND", "priority": 4}, {"ticker": "TOP", "priority": 5}]
    actions = generate_next_actions(None, watchlist, [], [])
    focus = [action["related_symbol"] for action in actions if action["type"] == "focus_watchlist"]
    assert focus == ["TOP", "FIRST"]


def test_empty_state_recommendations():
    """空态：推荐添加自选和持仓"""
    actions = generate_next_actions(
        portfolio_summary=None,
        watchlist_items=[],
        reports_to_review=[],
        alert_events=[],
    )

    assert len(actions) == 2
    assert any(a['type'] == 'add_watchlist' for a in actions)
    assert any(a['type'] == 'add_portfolio' for a in actions)

    add_watchlist = next(a for a in actions if a['type'] == 'add_watchlist')
    assert add_watchlist['severity'] == 'low'
    assert add_watchlist['target_route'] == '/watchlist'


def test_portfolio_risk_recommendations():
    """持仓亏损 >5% 触发风险提示"""
    portfolio = {
        'success': True,
        'positions': [
            {'ticker': 'AAPL', 'unrealized_pnl': -110, 'cost_basis': 1000},  # -11% → high
            {'ticker': 'NVDA', 'unrealized_pnl': -60, 'cost_basis': 1000},   # -6% → medium
            {'ticker': 'TSLA', 'unrealized_pnl': -30, 'cost_basis': 1000},   # -3% (不触发)
        ],
    }

    actions = generate_next_actions(
        portfolio_summary=portfolio,
        watchlist_items=[],
        reports_to_review=[],
        alert_events=[],
    )

    risk_actions = [a for a in actions if a['type'] == 'risk_check']
    assert len(risk_actions) == 2  # AAPL 和 NVDA

    aapl = next(a for a in risk_actions if a['related_symbol'] == 'AAPL')
    nvda = next(a for a in risk_actions if a['related_symbol'] == 'NVDA')

    assert aapl['severity'] == 'high'  # <-10% 为 high
    assert nvda['severity'] == 'medium'  # -5% ~ -10% 为 medium
    assert aapl['target_route'] == '/dashboard/AAPL'
    assert '亏损' in aapl['reason']


def test_stale_report_recommendations():
    """过期报告推荐刷新（最多 3 条）"""
    reports = [
        {'report_id': 'rep_1', 'ticker': 'AAPL', 'as_of': '2024-01-01', '_review_reasons': ['数据过期']},
        {'report_id': 'rep_2', 'ticker': 'NVDA', 'as_of': '2024-01-02', '_review_reasons': ['手动标记关注']},
        {'report_id': 'rep_3', 'ticker': 'TSLA', 'as_of': '2024-01-03', '_review_reasons': ['质检问题']},
        {'report_id': 'rep_4', 'ticker': 'MSFT', 'as_of': '2024-01-04', '_review_reasons': ['数据过期']},
    ]

    actions = generate_next_actions(
        portfolio_summary=None,
        watchlist_items=[],
        reports_to_review=reports,
        alert_events=[],
    )

    refresh_actions = [a for a in actions if a['type'] == 'refresh_report']
    assert len(refresh_actions) == 3  # 最多取前 3 个

    assert all(a['severity'] == 'medium' for a in refresh_actions)
    assert all('/reports?report_id=' in a['target_route'] for a in refresh_actions)


def test_alert_recommendations():
    """告警事件推荐查看（最多 2 条）"""
    alerts = [
        {'id': 'evt_1', 'ticker': 'AAPL', 'title': '价格异动', 'severity': 'high'},
        {'id': 'evt_2', 'ticker': 'NVDA', 'title': '新闻提醒', 'severity': 'medium'},
        {'id': 'evt_3', 'ticker': 'TSLA', 'title': '另一个提醒', 'severity': 'low'},
    ]

    actions = generate_next_actions(
        portfolio_summary=None,
        watchlist_items=[],
        reports_to_review=[],
        alert_events=alerts,
    )

    alert_actions = [a for a in actions if a['type'] == 'check_alert']
    assert len(alert_actions) == 2  # 最多取前 2 个

    assert alert_actions[0]['severity'] == 'high'
    assert alert_actions[1]['severity'] == 'medium'
    assert '/dashboard/' in alert_actions[0]['target_route']


def test_high_priority_watchlist_recommendations():
    """高优先级自选（≥4）推荐关注"""
    watchlist = [
        {'ticker': 'AAPL', 'priority': 5, 'watch_reason': '重点关注'},
        {'ticker': 'NVDA', 'priority': 4, 'watch_reason': 'AI 转型'},
        {'ticker': 'TSLA', 'priority': 3, 'watch_reason': None},  # 不触发
        {'ticker': 'MSFT', 'priority': 5, 'watch_reason': '财报前夕'},
        {'ticker': 'AMZN', 'priority': 4, 'watch_reason': '云业务'},
    ]

    actions = generate_next_actions(
        portfolio_summary=None,
        watchlist_items=watchlist,
        reports_to_review=[],
        alert_events=[],
    )

    focus_actions = [a for a in actions if a['type'] == 'focus_watchlist']
    assert len(focus_actions) == 2  # 最多取前 2 个

    assert all(a['severity'] == 'medium' for a in focus_actions)
    assert focus_actions[0]['related_symbol'] in ['AAPL', 'NVDA', 'MSFT', 'AMZN']


def test_watchlist_priority_none_is_ignored():
    """priority 为 None 的历史数据不应导致今日工作台崩溃。"""
    actions = generate_next_actions(
        portfolio_summary={"success": True, "positions": [{"ticker": "AAPL"}]},
        watchlist_items=[
            {"ticker": "AAPL", "priority": None, "watch_reason": "legacy data"},
            {"ticker": "MSFT", "priority": "", "watch_reason": "empty value"},
            {"ticker": "NVDA", "priority": "bad", "watch_reason": "bad value"},
        ],
        reports_to_review=[],
        alert_events=[],
    )

    assert [a for a in actions if a["type"] == "focus_watchlist"] == []


def test_research_status_generates_review_queue_action():
    actions = generate_next_actions(
        portfolio_summary={"success": True, "positions": [{"ticker": "AAPL"}]},
        watchlist_items=[
            {"ticker": "NVDA", "priority": 3, "research_status": "reviewing", "watch_reason": "需要复查 AI 需求证据"},
        ],
        reports_to_review=[],
        alert_events=[],
    )

    review_actions = [a for a in actions if a["type"] == "research_review"]
    assert len(review_actions) == 1
    assert review_actions[0]["related_symbol"] == "NVDA"
    assert review_actions[0]["target_route"] == "/dossier/NVDA"
    assert review_actions[0]["severity"] == "medium"


def test_severity_ordering():
    """验证操作按 severity 排序：critical > high > medium > low"""
    portfolio = {
        'success': True,
        'positions': [
            {'ticker': 'AAPL', 'unrealized_pnl': -150, 'cost_basis': 1000},  # high
        ],
    }
    reports = [
        {'report_id': 'rep_1', 'ticker': 'NVDA', '_review_reasons': ['过期']},  # medium
    ]
    alerts = [
        {'id': 'evt_1', 'ticker': 'TSLA', 'title': 'Alert', 'severity': 'high'},  # high
    ]
    watchlist = [
        {'ticker': 'MSFT', 'priority': 2, 'watch_reason': None},  # 不触发 focus
    ]

    actions = generate_next_actions(
        portfolio_summary=portfolio,
        watchlist_items=watchlist,
        reports_to_review=reports,
        alert_events=alerts,
    )

    # high severity 应该排在前面
    severities = [a['severity'] for a in actions]
    high_positions = [i for i, s in enumerate(severities) if s == 'high']
    medium_positions = [i for i, s in enumerate(severities) if s == 'medium']

    if high_positions and medium_positions:
        assert max(high_positions) < min(medium_positions), "high 应排在 medium 前"


def test_max_10_actions():
    """验证最多返回 10 条操作"""
    # 构造会产生 >10 条建议的数据
    portfolio = {
        'success': True,
        'positions': [
            {'ticker': f'TICK{i}', 'unrealized_pnl': -100, 'cost_basis': 1000}
            for i in range(8)
        ],
    }
    reports = [
        {'report_id': f'rep_{i}', 'ticker': f'SYM{i}', '_review_reasons': ['过期']}
        for i in range(5)
    ]

    actions = generate_next_actions(
        portfolio_summary=portfolio,
        watchlist_items=[],
        reports_to_review=reports,
        alert_events=[],
    )

    assert len(actions) <= 10
