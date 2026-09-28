# -*- coding: utf-8 -*-
"""services 的连接工厂（_conn/_connect）作为 with 上下文必须在退出时
真正关闭连接——裸 sqlite3.Connection 作 ctxmanager 只 commit 不 close，
句柄泄漏到外层函数结束；Windows 上还会挡住 os.replace（rollback 已证实）。"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


def _assert_closed(conn: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


def test_historical_conn_closes(tmp_path, monkeypatch):
    from backend.services import historical_data_store as module

    monkeypatch.setattr(module, "_DB_PATH", str(tmp_path / "hist.db"))
    with module._conn() as conn:
        conn.execute("CREATE TABLE t(x)")
    _assert_closed(conn)


def test_monitoring_connect_closes(tmp_path):
    from backend.services import monitoring_storage as module

    with module._connect(tmp_path / "mon.db") as conn:
        conn.execute("CREATE TABLE t(x)")
    _assert_closed(conn)


def test_portfolio_connect_closes(tmp_path, monkeypatch):
    from backend.services import portfolio_store as module

    monkeypatch.setattr(module, "_DB_PATH", tmp_path / "pf.db")
    with module._connect() as conn:
        conn.execute("SELECT 1")
    _assert_closed(conn)


def test_research_notes_connect_closes(tmp_path, monkeypatch):
    from backend.services import research_notes as module

    monkeypatch.setattr(module, "_DB_PATH", tmp_path / "rn.db")
    with module._connect() as conn:
        conn.execute("SELECT 1")
    _assert_closed(conn)


def test_notes_rag_conn_closes(tmp_path, monkeypatch):
    from backend.services import notes_rag as module

    monkeypatch.setattr(module, "_DB_PATH", tmp_path / "nr.db")
    with module._conn() as conn:
        conn.execute("SELECT 1")
    _assert_closed(conn)


def test_report_index_connect_closes(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORT_INDEX_SQLITE_PATH", str(tmp_path / "ri.db"))
    from backend.services.report_index import ReportIndexStore

    store = ReportIndexStore()
    with store._connect() as conn:
        conn.execute("SELECT 1")
    _assert_closed(conn)


def test_connect_closes_and_rolls_back_on_error(tmp_path):
    """异常路径：保持 with-conn 语义——rollback 且关闭。"""
    from backend.services import monitoring_storage as module

    db = tmp_path / "mon_rb.db"
    with module._connect(db) as conn:
        conn.execute("CREATE TABLE t(x)")
    with pytest.raises(RuntimeError):
        with module._connect(db) as conn:
            conn.execute("INSERT INTO t VALUES (1)")
            raise RuntimeError("boom")
    _assert_closed(conn)
    with module._connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 0


def test_db_file_can_be_replaced_after_with(tmp_path):
    """Windows 冒烟断言：with 退出后文件未被占用，可 os.replace。"""
    import os

    from backend.services import monitoring_storage as module

    db = tmp_path / "mon_replace.db"
    with module._connect(db) as conn:
        conn.execute("CREATE TABLE t(x)")
    replacement = tmp_path / "replacement.db"
    with module._connect(replacement) as conn:
        conn.execute("CREATE TABLE u(y)")
    os.replace(replacement, db)  # 句柄若泄漏则 PermissionError
    assert db.exists()
