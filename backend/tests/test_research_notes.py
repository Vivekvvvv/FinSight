# -*- coding: utf-8 -*-
"""测试 Research Notes 存储功能

使用项目实际数据库，测试后清理数据
"""
from backend.services import research_notes


def test_parse_tags_sanitizes_corrupt_and_legacy_values(caplog):
    assert research_notes._parse_tags("{bad-json") == []
    assert research_notes._parse_tags('{"tag": true}') == []
    assert research_notes._parse_tags('[" ok ", 1, "' + "x" * 100 + '"]') == [
        "ok",
        "x" * 64,
    ]
    assert caplog.text.count("invalid stored research note tags") == 2


def test_create_and_get_note():
    """测试创建和获取笔记"""
    # 创建笔记
    note_id = research_notes.create_note(
        session_id="pytest_session",
        user_id="pytest_user",
        title="AAPL Q1 财报分析",
        content="# 财报要点\n\n营收增长 10%",
        ticker="AAPL",
        tags=["财报", "科技"],
    )

    try:
        assert note_id.startswith("note_")

        # 获取笔记
        note = research_notes.get_note(note_id)
        assert note is not None
        assert note["title"] == "AAPL Q1 财报分析"
        assert note["ticker"] == "AAPL"
        assert note["tags"] == ["财报", "科技"]
        assert "营收增长" in note["content"]
    finally:
        # 清理测试数据
        research_notes.delete_note(note_id)


def test_update_note():
    """测试更新笔记"""
    note_id = research_notes.create_note(
        session_id="pytest_session",
        user_id="pytest_user",
        title="原标题",
        content="原内容",
    )

    try:
        # 更新标题
        success = research_notes.update_note(note_id, title="新标题")
        assert success is True

        note = research_notes.get_note(note_id)
        assert note["title"] == "新标题"
        assert note["content"] == "原内容"

        # 更新内容和标签
        success = research_notes.update_note(
            note_id,
            content="新内容",
            tags=["新标签"],
        )
        assert success is True

        note = research_notes.get_note(note_id)
        assert note["content"] == "新内容"
        assert note["tags"] == ["新标签"]
    finally:
        research_notes.delete_note(note_id)


def test_delete_note():
    """测试删除笔记（软删除）"""
    note_id = research_notes.create_note(
        session_id="pytest_session",
        user_id="pytest_user",
        title="待删除笔记",
    )

    # 删除笔记
    success = research_notes.delete_note(note_id)
    assert success is True

    # 删除后无法获取
    note = research_notes.get_note(note_id)
    assert note is None

    # 重复删除返回 False
    success = research_notes.delete_note(note_id)
    assert success is False


def test_list_notes():
    """测试列出笔记"""
    note_ids = []

    try:
        # 创建多条笔记
        note_ids.append(research_notes.create_note("pytest_session", "pytest_user", "笔记1", ticker="AAPL"))
        note_ids.append(research_notes.create_note("pytest_session", "pytest_user", "笔记2", ticker="AAPL"))
        note_ids.append(research_notes.create_note("pytest_session", "pytest_user", "笔记3", ticker="NVDA"))

        # 列出所有笔记
        notes = research_notes.list_notes("pytest_session", "pytest_user")
        pytest_notes = [n for n in notes if n["note_id"] in note_ids]
        assert len(pytest_notes) == 3

        # 按 ticker 筛选
        aapl_notes = research_notes.list_notes("pytest_session", "pytest_user", ticker="AAPL")
        pytest_aapl = [n for n in aapl_notes if n["note_id"] in note_ids]
        assert len(pytest_aapl) == 2

        nvda_notes = research_notes.list_notes("pytest_session", "pytest_user", ticker="NVDA")
        pytest_nvda = [n for n in nvda_notes if n["note_id"] in note_ids]
        assert len(pytest_nvda) == 1
    finally:
        for nid in note_ids:
            research_notes.delete_note(nid)


def test_search_notes():
    """测试搜索笔记"""
    note_ids = []

    try:
        # 创建笔记
        note_ids.append(research_notes.create_note(
            "pytest_session",
            "pytest_user",
            "AAPL 财报分析",
            content="营收增长强劲",
        ))
        note_ids.append(research_notes.create_note(
            "pytest_session",
            "pytest_user",
            "NVDA GPU 需求",
            content="AI 需求推动增长",
        ))

        # 搜索标题
        results = research_notes.search_notes("pytest_session", "pytest_user", "财报")
        pytest_results = [r for r in results if r["note_id"] in note_ids]
        assert len(pytest_results) == 1
        assert "AAPL" in pytest_results[0]["title"]

        # 搜索内容
        results = research_notes.search_notes("pytest_session", "pytest_user", "增长")
        pytest_results = [r for r in results if r["note_id"] in note_ids]
        assert len(pytest_results) == 2
    finally:
        for nid in note_ids:
            research_notes.delete_note(nid)
