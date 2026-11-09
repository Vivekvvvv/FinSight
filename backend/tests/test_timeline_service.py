# -*- coding: utf-8 -*-
"""Timeline Service Tests"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta

from backend.services import timeline_service, research_notes
from backend.services.report_index import get_report_index_store


@pytest.fixture
def clean_state():
    """清理测试状态"""
    # 测试前后清理笔记和报告
    yield
    # 清理由测试创建的数据
    # 注意：实际生产中应该用独立的测试数据库


@pytest.mark.parametrize("limit", [0, -1])
def test_empty_timeline_limits_stop_before_collecting_events(monkeypatch, limit):
    calls = []
    monkeypatch.setattr(timeline_service, "_collect_report_events", lambda *args: calls.append(args) or [])
    monkeypatch.setattr(timeline_service, "_collect_note_events", lambda *args: calls.append(args) or [])
    assert timeline_service.get_timeline("AAPL", "session", "user", limit=limit) == []
    assert calls == []


@pytest.mark.parametrize("summary", [123, {"text": "bad"}, ["bad"]])
def test_report_timeline_invalid_summary_does_not_break_event_list(monkeypatch, summary):
    from types import SimpleNamespace

    row = {"report_id": "r1", "generated_at": "2026-01-01T00:00:00Z", "summary": summary}
    monkeypatch.setattr(timeline_service, "get_report_index_store", lambda: SimpleNamespace(list_reports=lambda **kwargs: [row]))
    events = timeline_service.get_timeline("AAPL", "session", "user", event_type="report")
    assert len(events) == 1
    assert isinstance(events[0]["summary"], str)
    assert len(events[0]["summary"]) <= 200


@pytest.mark.parametrize("content", [123, {"text": "bad"}, ["bad"]])
def test_note_timeline_invalid_content_preserves_event_list(monkeypatch, content):
    row = {"note_id": "n1", "updated_at": "2026-01-01T00:00:00Z", "content": content, "tags": []}
    monkeypatch.setattr(research_notes, "list_notes", lambda **kwargs: [row])
    events = timeline_service.get_timeline("AAPL", "session", "user", event_type="note")
    assert len(events) == 1
    assert isinstance(events[0]["summary"], str)


@pytest.mark.parametrize("tags", [None, "风险", ["风险", None, 123]])
def test_note_timeline_tag_shapes_are_safe_and_preserve_risk_labels(monkeypatch, tags):
    row = {"note_id": "n1", "updated_at": "2026-01-01T00:00:00Z", "tags": tags}
    monkeypatch.setattr(research_notes, "list_notes", lambda **kwargs: [row])
    events = timeline_service.get_timeline("AAPL", "session", "user", event_type="note")
    assert len(events) == 1
    assert events[0]["severity"] == ("medium" if tags is None else "high")


@pytest.mark.parametrize("event_type", ["report", "note"])
def test_timeline_collectors_skip_malformed_rows(monkeypatch, event_type):
    from types import SimpleNamespace

    rows = [None, "bad", {"report_id": "r1", "note_id": "n1",
                           "generated_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z"}]
    monkeypatch.setattr(timeline_service, "get_report_index_store", lambda: SimpleNamespace(list_reports=lambda **kwargs: rows))
    monkeypatch.setattr(research_notes, "list_notes", lambda **kwargs: rows)
    events = timeline_service.get_timeline("AAPL", "session", "user", event_type=event_type)
    assert len(events) == 1
    assert events[0]["event_type"] == event_type


@pytest.mark.parametrize("event_type", ["report", "note"])
@pytest.mark.parametrize("identifier", [None, "", 123])
def test_timeline_rows_require_valid_source_identifiers(monkeypatch, event_type, identifier):
    from types import SimpleNamespace

    row = {"report_id": identifier, "note_id": identifier,
           "generated_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z"}
    monkeypatch.setattr(timeline_service, "get_report_index_store", lambda: SimpleNamespace(list_reports=lambda **kwargs: [row]))
    monkeypatch.setattr(research_notes, "list_notes", lambda **kwargs: [row])
    assert timeline_service.get_timeline("AAPL", "session", "user", event_type=event_type) == []


@pytest.mark.parametrize("marker", [{"success": False}, {"error": "unavailable"}])
def test_failed_report_records_do_not_become_timeline_events(monkeypatch, marker):
    from types import SimpleNamespace

    row = {"report_id": "r1", "generated_at": "2026-01-01T00:00:00Z", **marker}
    monkeypatch.setattr(timeline_service, "get_report_index_store", lambda: SimpleNamespace(list_reports=lambda **kwargs: [row]))
    assert timeline_service.get_timeline("AAPL", "session", "user", event_type="report") == []


def test_timeline_citation_count_cannot_be_negative(monkeypatch):
    from types import SimpleNamespace

    row = {"report_id": "r1", "generated_at": "2026-01-01T00:00:00Z", "citation_count": -10}
    monkeypatch.setattr(timeline_service, "get_report_index_store", lambda: SimpleNamespace(list_reports=lambda **kwargs: [row]))
    event = timeline_service.get_timeline("AAPL", "session", "user", event_type="report")[0]
    assert event["evidence"]["citation_count"] == 0


def test_timezone_offset_order_uses_actual_instant(monkeypatch):
    events = [
        {"id": "older", "occurred_at": "2026-01-02T08:00:00+08:00"},
        {"id": "newer", "occurred_at": "2026-01-02T01:00:00+00:00"},
    ]
    monkeypatch.setattr(timeline_service, "_collect_report_events", lambda *args: events)
    actual = timeline_service.get_timeline("AAPL", "s", "u", event_type="report", limit=1)
    assert [event["id"] for event in actual] == ["newer"]


def test_persisted_confidence_is_numeric_and_finite(monkeypatch):
    from types import SimpleNamespace
    import json
    for raw, expected in (("0.9", 0.9), ("nan", None), (float("inf"), None), (True, None), (2, None)):
        row = {"report_id": "r1", "generated_at": "2026-01-01T00:00:00Z", "confidence_score": raw}
        monkeypatch.setattr(timeline_service, "get_report_index_store", lambda: SimpleNamespace(list_reports=lambda **kwargs: [row]))
        events = timeline_service.get_timeline("AAPL", "s", "u", event_type="report")
        assert events[0]["evidence"]["confidence"] == expected
        json.dumps(events, allow_nan=False)


def test_empty_timeline(clean_state):
    """测试 1：空数据返回空列表"""
    events = timeline_service.get_timeline(
        symbol="TSLA",
        session_id="test_empty_session",
        user_id="test_empty_user",
        limit=50,
    )

    assert isinstance(events, list)
    assert len(events) == 0


def test_report_events_conversion(clean_state):
    """测试 2：Reports 转换为 report 事件"""
    session_id = "test_report_session"
    store = get_report_index_store()

    # 创建测试报告
    report_id = "test_report_aapl_001"
    result = store.upsert_report(
        session_id=session_id,
        report={
            "report_id": report_id,
            "ticker": "AAPL",
            "title": "测试报告",
            "summary": "这是一份测试报告",
            "content": "详细内容",
            "confidence_score": 0.85,
        }
    )

    # 获取时间线
    events = timeline_service.get_timeline(
        symbol="AAPL",
        session_id=session_id,
        user_id="test_user",
        limit=50,
    )

    # 验证
    assert len(events) >= 1
    report_event = next((e for e in events if e["event_type"] == "report"), None)
    assert report_event is not None
    assert report_event["symbol"] == "AAPL"
    assert "测试报告" in report_event["title"]
    assert report_event["related_report_id"] == report_id
    assert "confidence" in report_event["evidence"]


def test_note_events_conversion(clean_state):
    """测试 3：Notes 转换为 note 事件"""
    session_id = "test_note_session"
    user_id = "test_note_user"

    # 创建测试笔记
    note_id = research_notes.create_note(
        session_id=session_id,
        user_id=user_id,
        ticker="MSFT",
        title="MSFT 研究笔记",
        content="这是一份研究笔记内容",
        tags=["财报", "分析"],
    )

    try:
        # 获取时间线
        events = timeline_service.get_timeline(
            symbol="MSFT",
            session_id=session_id,
            user_id=user_id,
            limit=50,
        )

        # 验证
        assert len(events) >= 1
        note_event = next((e for e in events if e["event_type"] == "note"), None)
        assert note_event is not None
        assert note_event["symbol"] == "MSFT"
        assert "MSFT 研究笔记" in note_event["title"]
        assert note_event["related_note_id"] == note_id

    finally:
        # 清理
        research_notes.delete_note(note_id)


def test_event_type_filter_report(clean_state):
    """测试 4：event_type 过滤 - 只返回 report"""
    session_id = "test_filter_session"
    user_id = "test_filter_user"
    store = get_report_index_store()

    # 创建报告和笔记
    report_id = "test_report_googl_001"
    result = store.upsert_report(
        session_id=session_id,
        report={
            "report_id": report_id,
            "ticker": "GOOGL",
            "title": "GOOGL 报告",
            "summary": "报告摘要",
        }
    )

    note_id = research_notes.create_note(
        session_id=session_id,
        user_id=user_id,
        ticker="GOOGL",
        title="GOOGL 笔记",
        content="笔记内容",
    )

    try:
        # 只获取 report 类型
        events = timeline_service.get_timeline(
            symbol="GOOGL",
            session_id=session_id,
            user_id=user_id,
            event_type="report",
            limit=50,
        )

        # 验证
        assert len(events) >= 1
        assert all(e["event_type"] == "report" for e in events)
        assert any(e["related_report_id"] == report_id for e in events)
        assert not any(e.get("related_note_id") == note_id for e in events)

    finally:
        research_notes.delete_note(note_id)


def test_event_type_filter_note(clean_state):
    """测试 5：event_type 过滤 - 只返回 note"""
    session_id = "test_filter_note_session"
    user_id = "test_filter_note_user"
    store = get_report_index_store()

    # 创建报告和笔记
    report_id = "test_report_nvda_001"
    result = store.upsert_report(
        session_id=session_id,
        report={
            "report_id": report_id,
            "ticker": "NVDA",
            "title": "NVDA 报告",
            "summary": "报告摘要",
        }
    )

    note_id = research_notes.create_note(
        session_id=session_id,
        user_id=user_id,
        ticker="NVDA",
        title="NVDA 笔记",
        content="笔记内容",
    )

    try:
        # 只获取 note 类型
        events = timeline_service.get_timeline(
            symbol="NVDA",
            session_id=session_id,
            user_id=user_id,
            event_type="note",
            limit=50,
        )

        # 验证
        assert len(events) >= 1
        assert all(e["event_type"] == "note" for e in events)
        assert any(e.get("related_note_id") == note_id for e in events)
        assert not any(e.get("related_report_id") == report_id for e in events)

    finally:
        research_notes.delete_note(note_id)


def test_limit_parameter(clean_state):
    """测试 6：limit 参数生效"""
    session_id = "test_limit_session"
    user_id = "test_limit_user"

    # 创建多条笔记
    note_ids = []
    for i in range(5):
        note_id = research_notes.create_note(
            session_id=session_id,
            user_id=user_id,
            ticker="AMZN",
            title=f"AMZN 笔记 {i+1}",
            content=f"笔记内容 {i+1}",
        )
        note_ids.append(note_id)

    try:
        # 测试 limit=3
        events = timeline_service.get_timeline(
            symbol="AMZN",
            session_id=session_id,
            user_id=user_id,
            limit=3,
        )

        # 验证
        assert len(events) == 3

    finally:
        # 清理
        for note_id in note_ids:
            research_notes.delete_note(note_id)


def test_occurred_at_descending_order(clean_state):
    """测试 7：occurred_at 倒序排序"""
    session_id = "test_order_session"
    user_id = "test_order_user"
    store = get_report_index_store()

    # 创建3条笔记（时间间隔）
    note_ids = []
    import time
    for i in range(3):
        note_id = research_notes.create_note(
            session_id=session_id,
            user_id=user_id,
            ticker="META",
            title=f"META 笔记 {i+1}",
            content=f"按顺序创建 {i+1}",
        )
        note_ids.append(note_id)
        time.sleep(0.1)  # 确保时间戳不同

    try:
        # 获取时间线
        events = timeline_service.get_timeline(
            symbol="META",
            session_id=session_id,
            user_id=user_id,
            limit=50,
        )

        # 验证倒序（最新的在前）
        assert len(events) >= 3
        timestamps = [e["occurred_at"] for e in events]
        assert timestamps == sorted(timestamps, reverse=True), "事件应按 occurred_at 倒序排列"

    finally:
        for note_id in note_ids:
            research_notes.delete_note(note_id)


def test_time_range_filter(clean_state):
    """测试 8：时间范围过滤"""
    session_id = "test_time_range_session"
    user_id = "test_time_range_user"

    # 创建笔记
    note_id = research_notes.create_note(
        session_id=session_id,
        user_id=user_id,
        ticker="TSLA",
        title="TSLA 当前笔记",
        content="当前时间笔记",
    )

    try:
        # 设置未来时间范围（应该查询不到）
        future_date = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

        events = timeline_service.get_timeline(
            symbol="TSLA",
            session_id=session_id,
            user_id=user_id,
            from_date=future_date,
            limit=50,
        )

        # 验证：未来时间范围查询不到当前笔记
        assert len(events) == 0

        # 设置过去到现在的时间范围（应该能查到）
        past_date = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

        events = timeline_service.get_timeline(
            symbol="TSLA",
            session_id=session_id,
            user_id=user_id,
            from_date=past_date,
            limit=50,
        )

        # 验证：能查到笔记
        assert len(events) >= 1

    finally:
        research_notes.delete_note(note_id)


def test_naive_generated_at_does_not_crash_range_filter(clean_state):
    """report/ir.py、report/validator.py、report_generator.py 用
    datetime.now().isoformat() 写 naive generated_at（无时区）。
    from_date 为 aware ISO 时 occurred_at < from_dt 比较抛 TypeError
    → /api/timeline 与 /api/what-changed（恒传 aware from_date）500。"""
    session_id = "test_naive_ts_session"
    user_id = "test_naive_ts_user"
    store = get_report_index_store()

    store.upsert_report(
        session_id=session_id,
        report={
            "report_id": "test_naive_generated_at_001",
            "ticker": "NAIVECO",
            "title": "naive 时间报告",
            "summary": "有摘要",
            # 与 report_generator.py:46 同款的 naive 时间戳
            "generated_at": datetime.now().isoformat(),
        },
    )

    from_date = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    events = timeline_service.get_timeline(
        symbol="NAIVECO",
        session_id=session_id,
        user_id=user_id,
        from_date=from_date,
        limit=50,
    )

    assert len(events) == 1
    assert events[0]["related_report_id"] == "test_naive_generated_at_001"


def test_null_summary_does_not_crash(clean_state):
    """report_index 的 summary/title 列可空：存 NULL 时
    .get(k, 默认) 拿到 None → None[:200] 抛 TypeError → timeline 500。"""
    session_id = "test_null_summary_session"
    user_id = "test_null_summary_user"
    store = get_report_index_store()

    store.upsert_report(
        session_id=session_id,
        report={
            "report_id": "test_null_summary_001",
            "ticker": "NULLSUM",
            "title": "无摘要报告",
            # 不传 summary → 存 NULL
        },
    )

    events = timeline_service.get_timeline(
        symbol="NULLSUM",
        session_id=session_id,
        user_id=user_id,
        limit=50,
    )

    assert len(events) == 1
    assert events[0]["related_report_id"] == "test_null_summary_001"
    assert events[0]["summary"] == ""
