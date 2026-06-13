# -*- coding: utf-8 -*-
"""测试 next_actions 推荐引擎"""
from backend.services.next_actions import generate_next_actions


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
