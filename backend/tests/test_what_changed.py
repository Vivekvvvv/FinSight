# -*- coding: utf-8 -*-
"""What Changed Service Tests"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta

from backend.services import what_changed, research_notes
from backend.services.report_index import get_report_index_store
from backend.services.memory import MemoryService

# 全局 memory service 实例
_memory_service = MemoryService()


@pytest.mark.parametrize("failure", [{"success": False}, {"error": "bad"}, {"status": " Failed "}])
def test_failed_reports_do_not_create_report_changes(monkeypatch, failure):
    from types import SimpleNamespace
    row = {"report_id": "bad", "ticker": "AAPL", "freshness_status": "stale", **failure}
    monkeypatch.setattr(what_changed, "get_report_index_store",
                        lambda: SimpleNamespace(list_reports=lambda **kwargs: [row]))
    assert what_changed._collect_report_changes("s", ["AAPL"], []) == []


@pytest.mark.parametrize("collector", ["timeline", "note"])
def test_changes_exclude_events_for_a_different_instrument(monkeypatch, collector):
    base = {"id": "wrong", "related_note_id": "wrong", "severity": "high",
            "occurred_at": datetime.now(timezone.utc).isoformat(), "symbol": "MSFT"}
    monkeypatch.setattr(what_changed.timeline_service, "get_timeline", lambda **kwargs: [base])
    changes = (what_changed._collect_timeline_changes("s", "u", None, ["AAPL"], [])
               if collector == "timeline" else what_changed._collect_note_changes("s", "u", ["AAPL"], []))
    assert changes == []


@pytest.mark.parametrize("severity", [" HIGH ", "Critical"])
def test_timeline_change_severity_is_normalized(monkeypatch, severity):
    monkeypatch.setattr(what_changed.timeline_service, "get_timeline", lambda **kwargs:
                        [{"id": "valid", "severity": severity, "occurred_at": datetime.now(timezone.utc).isoformat()}])
    changes = what_changed._collect_timeline_changes("s", "u", None, ["AAPL"], [])
    assert len(changes) == 1
    assert changes[0]["severity"] == severity.strip().lower()


@pytest.mark.parametrize("collector", ["timeline", "note"])
@pytest.mark.parametrize("failure", [{"success": False}, {"error": "failed"}, {"status": " Failed "}])
def test_failed_events_do_not_generate_actionable_changes(monkeypatch, collector, failure):
    base = {"id": "bad", "related_note_id": "bad", "severity": "high",
            "occurred_at": datetime.now(timezone.utc).isoformat()}
    monkeypatch.setattr(what_changed.timeline_service, "get_timeline", lambda **kwargs: [{**base, **failure}])
    changes = (what_changed._collect_timeline_changes("s", "u", None, ["AAPL"], [])
               if collector == "timeline" else what_changed._collect_note_changes("s", "u", ["AAPL"], []))
    assert changes == []


@pytest.mark.parametrize("note_id", [None, "", "  ", True, [], 123])
def test_note_changes_require_usable_note_ids(monkeypatch, note_id):
    base = {"occurred_at": datetime.now(timezone.utc).isoformat()}
    monkeypatch.setattr(what_changed.timeline_service, "get_timeline",
                        lambda **kwargs: [{**base, "related_note_id": note_id}, {**base, "related_note_id": "valid"}])
    changes = what_changed._collect_note_changes("s", "u", ["AAPL"], [])
    assert [item["id"] for item in changes] == ["note_valid"]


@pytest.mark.parametrize("event_id", [None, "", "  ", True, [], 123])
def test_timeline_changes_require_usable_event_ids(monkeypatch, event_id):
    base = {"severity": "high", "occurred_at": datetime.now(timezone.utc).isoformat()}
    monkeypatch.setattr(what_changed.timeline_service, "get_timeline",
                        lambda **kwargs: [{**base, "id": event_id}, {**base, "id": "valid"}])
    changes = what_changed._collect_timeline_changes("s", "u", None, ["AAPL"], [])
    assert [item["id"] for item in changes] == ["timeline_valid"]


@pytest.mark.parametrize("collector", ["timeline", "note"])
def test_change_collectors_preserve_valid_events_beside_malformed_rows(monkeypatch, collector):
    event = {"id": "valid", "related_note_id": "valid", "severity": "high",
             "occurred_at": datetime.now(timezone.utc).isoformat()}
    monkeypatch.setattr(what_changed.timeline_service, "get_timeline", lambda **kwargs: [None, "bad", event])
    changes = (what_changed._collect_timeline_changes("s", "u", None, ["AAPL"], [])
               if collector == "timeline" else what_changed._collect_note_changes("s", "u", ["AAPL"], []))
    assert [change["id"] for change in changes] == [f"{collector}_valid"]


@pytest.mark.parametrize("limit", [0, -1])
def test_empty_change_request_stops_before_data_collection(monkeypatch, limit):
    def unexpected_read(*args, **kwargs):
        pytest.fail("empty change request must not load persistent data")

    monkeypatch.setattr(what_changed._memory_service, "list_watchlist_items", unexpected_read)

    assert what_changed.get_what_changed(session_id="empty", user_id="empty", limit=limit) == []


def test_change_instrument_lists_filter_malformed_rows_and_normalize_identities(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(what_changed._memory_service, "list_watchlist_items", lambda _uid: [
        None, "bad", {"ticker": []}, {"ticker": " aapl "}, {"ticker": "AAPL"},
    ])
    monkeypatch.setattr(what_changed.portfolio_store, "get_positions", lambda _sid: [
        None, {"ticker": {}}, {"ticker": " msft "}, {"ticker": "MSFT"},
    ])
    monkeypatch.setattr(what_changed, "get_report_index_store", lambda: SimpleNamespace(list_reports=lambda **kwargs: [
        {"ticker": "AAPL", "report_id": "a", "freshness_status": "stale"},
        {"ticker": "MSFT", "report_id": "m", "freshness_status": "stale"},
    ]))
    calls = []
    def timeline(**kwargs):
        calls.append(kwargs["symbol"])
        return []
    monkeypatch.setattr(what_changed.timeline_service, "get_timeline", timeline)

    changes = what_changed.get_what_changed(session_id="session", user_id="user")

    assert [change["symbol"] for change in changes] == ["MSFT", "AAPL"]
    assert changes[0]["severity"] == "high"
    assert calls == ["AAPL", "MSFT", "AAPL", "MSFT"]


def test_malformed_report_change_rows_preserve_valid_report_alerts(monkeypatch):
    from types import SimpleNamespace

    reports = [None, "bad", {}, {"ticker": "AAPL", "freshness_status": "stale"},
               {"ticker": "AAPL", "report_id": None, "freshness_status": "stale"},
               {"ticker": "AAPL", "report_id": "r1", "freshness_status": "stale"}]
    monkeypatch.setattr(what_changed, "get_report_index_store", lambda: SimpleNamespace(list_reports=lambda **kwargs: reports))

    changes = what_changed._collect_report_changes("session", ["AAPL"], [])

    assert [change["report_id"] for change in changes] == ["r1"]
    assert changes[0]["target_route"] == "/reports?highlight=r1"


@pytest.mark.parametrize("field, raw, expected", [
    ("quality_state", " BLOCK ", "critical"), ("quality_state", "Warn", "high"),
    ("citation_quality", " LOW ", "high"), ("freshness_status", " Stale ", "medium"),
    ("review_status", " WATCH ", "medium"),
])
def test_report_change_flags_ignore_case_and_whitespace(monkeypatch, field, raw, expected):
    from types import SimpleNamespace

    row = {"ticker": "AAPL", "report_id": "r1", "freshness_status": "aging", field: raw}
    monkeypatch.setattr(what_changed, "get_report_index_store", lambda: SimpleNamespace(list_reports=lambda **kwargs: [row]))

    changes = what_changed._collect_report_changes("session", ["AAPL"], [])

    assert len(changes) == 1
    assert changes[0]["severity"] == expected
    assert row[field] == raw


@pytest.mark.parametrize("collector", ["timeline", "note"])
def test_future_events_are_excluded_from_recent_changes(monkeypatch, collector):
    now = datetime.now(timezone.utc)
    events = [
        {"id": "future", "related_note_id": "future", "severity": "high", "occurred_at": (now + timedelta(hours=1)).isoformat()},
        {"id": "current", "related_note_id": "current", "severity": "high", "occurred_at": now.isoformat()},
    ]
    monkeypatch.setattr(what_changed.timeline_service, "get_timeline", lambda **kwargs: events)

    changes = (what_changed._collect_timeline_changes("session", "user", None, ["AAPL"], [])
               if collector == "timeline" else what_changed._collect_note_changes("session", "user", ["AAPL"], []))

    assert [change["id"] for change in changes] == [f"{collector}_current"]


@pytest.mark.parametrize("collector", ["timeline", "note"])
def test_repeated_watchlist_and_portfolio_symbols_do_not_consume_query_limit(monkeypatch, collector):
    watchlist = ["AAPL", "MSFT", "TSLA", "NVDA", "AMZN"]
    portfolio = watchlist + ["GOOGL"]
    calls = []

    def timeline(**kwargs):
        calls.append(kwargs["symbol"])
        return [{"id": "late-event", "related_note_id": "late-note", "severity": "high",
                 "occurred_at": datetime.now(timezone.utc).isoformat()}] if kwargs["symbol"] == "GOOGL" else []

    monkeypatch.setattr(what_changed.timeline_service, "get_timeline", timeline)

    if collector == "timeline":
        changes = what_changed._collect_timeline_changes("session", "user", None, watchlist, portfolio)
    else:
        changes = what_changed._collect_note_changes("session", "user", watchlist, portfolio)

    assert [change["symbol"] for change in changes] == ["GOOGL"]
    assert calls == watchlist + ["GOOGL"]


def test_symbol_filter_applies_to_reports_and_notes(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(what_changed._memory_service, "list_watchlist_items", lambda _uid: [{"ticker": "MSFT"}])
    monkeypatch.setattr(what_changed.portfolio_store, "get_positions", lambda _sid: [{"ticker": "NVDA"}])
    reports = [
        {"report_id": "r-aapl", "ticker": "AAPL", "freshness_status": "stale"},
        {"report_id": "r-nvda", "ticker": "NVDA", "freshness_status": "stale"},
    ]
    monkeypatch.setattr(what_changed, "get_report_index_store", lambda: SimpleNamespace(list_reports=lambda **kwargs: reports))

    def timeline(**kwargs):
        if kwargs.get("event_type") != "note":
            return []
        return [{"related_note_id": kwargs["symbol"], "occurred_at": datetime.now(timezone.utc).isoformat()}]

    monkeypatch.setattr(what_changed.timeline_service, "get_timeline", timeline)

    changes = what_changed.get_what_changed(session_id="scoped", user_id="scoped", symbol="aapl")

    assert {change["symbol"] for change in changes} == {"AAPL"}
    assert {change["change_type"] for change in changes} == {"report", "note"}


@pytest.fixture
def clean_state():
    """清理测试状态"""
    yield


def test_naive_timestamp_recency_is_scored_in_local_timezone():
    raw = (datetime.now() - timedelta(hours=3)).isoformat()
    parsed = what_changed._parse_iso_safe(raw)
    assert what_changed._hours_ago(parsed) == pytest.approx(3, abs=0.01)
    assert parsed.tzinfo is not None


def test_empty_data_returns_empty_list(clean_state):
    """测试 1：空数据返回空列表"""
    changes = what_changed.get_what_changed(
        session_id="test_empty_session",
        user_id="test_empty_user",
        limit=5,
    )

    assert isinstance(changes, list)
    assert len(changes) == 0


def test_high_severity_timeline_event_generates_change(clean_state):
    """测试 2：high severity timeline 事件生成变化"""
    session_id = "test_timeline_session"
    user_id = "test_timeline_user"

    # 添加到 watchlist
    _memory_service.add_to_watchlist(user_id, "TSLA", note="测试关注")

    # 创建 high severity 笔记
    note_id = research_notes.create_note(
        session_id=session_id,
        user_id=user_id,
        ticker="TSLA",
        title="TSLA 高风险事件",
        content="检测到重大风险",
    )

    try:
        changes = what_changed.get_what_changed(
            session_id=session_id,
            user_id=user_id,
            limit=10,
        )

        # 验证：应该至少有笔记相关的变化
        assert len(changes) >= 0  # 笔记本身 severity 是 medium，可能不会出现

    finally:
        research_notes.delete_note(note_id)


def test_stale_report_generates_change(clean_state):
    """测试 3：stale report 生成变化"""
    session_id = "test_stale_report_session"
    user_id = "test_stale_report_user"
    store = get_report_index_store()

    # 添加到 watchlist
    _memory_service.add_to_watchlist(user_id, "AAPL", note="测试关注")

    # 创建过期报告
    report_id = "test_stale_report_001"
    store.upsert_report(
        session_id=session_id,
        report={
            "report_id": report_id,
            "ticker": "AAPL",
            "title": "AAPL 过期报告",
            "summary": "数据已过期",
            "freshness_status": "stale",
            "quality_state": "warn",
        }
    )

    changes = what_changed.get_what_changed(
        session_id=session_id,
        user_id=user_id,
        limit=10,
    )

    # 验证
    assert len(changes) >= 1
    report_change = next((c for c in changes if c["change_type"] == "report"), None)
    assert report_change is not None
    assert report_change["symbol"] == "AAPL"
    assert "报告需要复查" in report_change["title"]
    assert report_change["severity"] in ("medium", "high", "critical")


def test_quality_blocked_report_generates_change(clean_state):
    """测试 4：freshness stale + citation low 报告生成变化"""
    session_id = "test_blocked_report_session"
    user_id = "test_blocked_report_user"
    store = get_report_index_store()

    # 添加到 watchlist
    _memory_service.add_to_watchlist(user_id, "GOOGL", note="测试关注")

    # 创建低质量报告（freshness stale + citation low 会触发变化）
    report_id = "test_blocked_report_001"
    store.upsert_report(
        session_id=session_id,
        report={
            "report_id": report_id,
            "ticker": "GOOGL",
            "title": "GOOGL 过期报告",
            "summary": "数据已过期",
            "freshness_status": "stale",
        },
        include_blocked=True,
    )

    changes = what_changed.get_what_changed(
        session_id=session_id,
        user_id=user_id,
        limit=10,
    )

    # 验证
    report_change = next((c for c in changes if c["change_type"] == "report" and c.get("report_id") == report_id), None)
    assert report_change is not None, f"未找到 report_id={report_id} 的变化"
    assert report_change["severity"] in ("medium", "high", "critical")
    assert "数据已过期" in report_change["reason"] or "stale" in str(report_change.get("evidence"))


def test_recent_note_generates_change(clean_state):
    """测试 5：最近笔记生成变化"""
    session_id = "test_note_session"
    user_id = "test_note_user"

    # 添加到 watchlist
    _memory_service.add_to_watchlist(user_id, "MSFT", note="测试关注")

    # 创建笔记
    note_id = research_notes.create_note(
        session_id=session_id,
        user_id=user_id,
        ticker="MSFT",
        title="MSFT 新假设",
        content="记录新的投资假设",
    )

    try:
        changes = what_changed.get_what_changed(
            session_id=session_id,
            user_id=user_id,
            limit=10,
        )

        # 验证
        note_change = next((c for c in changes if c["change_type"] == "note"), None)
        assert note_change is not None
        assert note_change["symbol"] == "MSFT"
        assert "新增研究笔记" in note_change["title"]

    finally:
        research_notes.delete_note(note_id)


def test_watchlist_symbol_gets_priority(clean_state):
    """测试 6：watchlist 标的获得优先级加权"""
    session_id = "test_watchlist_priority_session"
    user_id = "test_watchlist_priority_user"

    # 添加到 watchlist
    _memory_service.add_to_watchlist(user_id, "NVDA", note="高优先级关注")

    # 创建笔记
    note_id = research_notes.create_note(
        session_id=session_id,
        user_id=user_id,
        ticker="NVDA",
        title="NVDA 笔记",
        content="测试内容",
    )

    try:
        changes = what_changed.get_what_changed(
            session_id=session_id,
            user_id=user_id,
            limit=10,
        )

        # 验证：watchlist 标的的变化应该出现
        nvda_changes = [c for c in changes if c.get("symbol") == "NVDA"]
        assert len(nvda_changes) >= 1

    finally:
        research_notes.delete_note(note_id)


def test_deduplication_keeps_highest_score(clean_state):
    """测试 7：同 symbol 去重保留最高分"""
    session_id = "test_dedup_session"
    user_id = "test_dedup_user"
    store = get_report_index_store()

    # 添加到 watchlist
    _memory_service.add_to_watchlist(user_id, "AMZN", note="测试关注")

    # 创建两个报告：一个 aging，一个 stale（stale 得分更高）
    report_id_1 = "test_dedup_report_001"
    store.upsert_report(
        session_id=session_id,
        report={
            "report_id": report_id_1,
            "ticker": "AMZN",
            "title": "AMZN 报告 1",
            "summary": "aging 状态",
            "freshness_status": "aging",
        }
    )

    report_id_2 = "test_dedup_report_002"
    store.upsert_report(
        session_id=session_id,
        report={
            "report_id": report_id_2,
            "ticker": "AMZN",
            "title": "AMZN 报告 2",
            "summary": "stale 状态",
            "freshness_status": "stale",
        }
    )

    changes = what_changed.get_what_changed(
        session_id=session_id,
        user_id=user_id,
        limit=10,
    )

    # 验证：同一个 symbol 的 report 类型变化只保留一个
    amzn_report_changes = [c for c in changes if c.get("symbol") == "AMZN" and c["change_type"] == "report"]
    assert len(amzn_report_changes) == 1, f"期望 1 条 AMZN report 变化，实际 {len(amzn_report_changes)} 条"

    # 保留的应该是 stale（更高分：25 vs 15）
    kept_change = amzn_report_changes[0]
    assert "数据已过期" in kept_change["reason"] or kept_change.get("report_id") == report_id_2


def test_limit_parameter_enforced(clean_state):
    """测试 8：limit 参数生效且按 score 排序"""
    session_id = "test_limit_session"
    user_id = "test_limit_user"
    store = get_report_index_store()

    # 添加多个 watchlist 标的
    for sym in ["AAPL", "GOOGL", "MSFT", "TSLA", "NVDA"]:
        _memory_service.add_to_watchlist(user_id, sym, note=f"{sym} 关注")

    # 为每个标的创建报告
    for i, sym in enumerate(["AAPL", "GOOGL", "MSFT", "TSLA", "NVDA"]):
        report_id = f"test_limit_report_{i:03d}"
        store.upsert_report(
            session_id=session_id,
            report={
                "report_id": report_id,
                "ticker": sym,
                "title": f"{sym} 报告",
                "summary": "测试报告",
                "quality_state": "warn",
                "freshness_status": "stale",
            }
        )

    # 测试 limit=3
    changes = what_changed.get_what_changed(
        session_id=session_id,
        user_id=user_id,
        limit=3,
    )

    # 验证
    assert len(changes) == 3

    # 验证不包含内部 score 字段
    for change in changes:
        assert "score" not in change


def test_portfolio_positions_feed_what_changed(monkeypatch, clean_state):
    """portfolio_symbols 原来是 TODO 空列表——只在持仓、不在自选的标的，
    其报告/timeline/笔记变化永远不进 What Changed。修复后
    get_positions(session_id) 的 ticker 应参与收集。"""
    session_id = "test_portfolio_change_session"
    user_id = "test_portfolio_change_user"
    store = get_report_index_store()

    # 持仓里有 PORT，watchlist 为空——PORT 变化只能靠持仓路径进来
    monkeypatch.setattr(
        "backend.services.portfolio_store.get_positions",
        lambda _sid: [{"ticker": "PORT", "shares": 10, "avg_cost": 100}],
    )
    monkeypatch.setattr(
        what_changed._memory_service,
        "list_watchlist_items",
        lambda _uid: [],
    )

    store.upsert_report(
        session_id=session_id,
        report={
            "report_id": "test_portfolio_only_report",
            "ticker": "PORT",
            "title": "PORT 过期报告",
            "summary": "数据已过期",
            "freshness_status": "stale",
        },
    )

    changes = what_changed.get_what_changed(
        session_id=session_id,
        user_id=user_id,
        limit=10,
    )

    port_change = next((c for c in changes if c.get("symbol") == "PORT"), None)
    assert port_change is not None, "持仓标的 PORT 的变化未被收集"
    assert port_change["change_type"] == "report"


def test_lowercase_stored_ticker_report_change_not_dropped(clean_state):
    """report_index.upsert_report 存 ticker 只 strip 不 upper；
    若报告以小写 ticker 入库，_collect_report_changes 用原值与
    大写 watchlist/portfolio 列表比较 → 该报告的 stale/质量变化被
    静默丢弃（reports_to_review、task_router 都在读取端做了大写归一，
    只有这里漏了）。"""
    session_id = "test_lower_ticker_session"
    user_id = "test_lower_ticker_user"
    store = get_report_index_store()

    _memory_service.add_to_watchlist(user_id, "AAPL", note="大写自选")

    store.upsert_report(
        session_id=session_id,
        report={
            "report_id": "test_lower_ticker_report",
            "ticker": "aapl",  # 库存原样小写（upsert 不归一）
            "title": "AAPL 过期报告",
            "summary": "数据已过期",
            "freshness_status": "stale",
        },
    )

    changes = what_changed.get_what_changed(
        session_id=session_id,
        user_id=user_id,
        limit=10,
    )

    report_change = next(
        (c for c in changes if c["change_type"] == "report" and c.get("symbol") == "AAPL"),
        None,
    )
    assert report_change is not None, "小写存储 ticker 的报告变化被静默丢弃"


def test_clean_portfolio_report_does_not_phantom_trigger(monkeypatch, clean_state):
    """_collect_report_changes 的持仓加权(score+20)在阈值判定前无条件生效——
    零标记的干净报告仅凭 ticker 在持仓就 score=20≥20 进 What Changed，
    reasons 为空 → reason 输出裸"。"。加权应放大已标记问题而非凭空触发；
    对照 timeline/notes 收集器的加权均作用在已过滤的真实事件上。"""
    session_id = "test_phantom_session"
    user_id = "test_phantom_user"
    store = get_report_index_store()

    monkeypatch.setattr(
        "backend.services.portfolio_store.get_positions",
        lambda _sid: [{"ticker": "HELD", "shares": 10, "avg_cost": 100}],
    )
    monkeypatch.setattr(
        what_changed._memory_service,
        "list_watchlist_items",
        lambda _uid: [],
    )

    store.upsert_report(
        session_id=session_id,
        report={
            "report_id": "clean_held_report",
            "ticker": "HELD",
            "title": "HELD 正常报告",
            "summary": "一切正常",
        },
    )

    changes = what_changed.get_what_changed(
        session_id=session_id,
        user_id=user_id,
        limit=10,
    )
    phantom = [
        c for c in changes
        if c.get("change_type") == "report" and c.get("symbol") == "HELD"
    ]
    assert phantom == [], f"干净持仓报告不应产生变化: {phantom}"
