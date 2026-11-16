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


def test_historical_connection_closes_when_journal_setup_fails(tmp_path, monkeypatch):
    from backend.services import historical_data_store as module

    class BrokenConnection:
        closed = False

        def execute(self, _statement):
            raise sqlite3.OperationalError("simulated journal setup failure")

        def rollback(self):
            pass

        def close(self):
            self.closed = True

    connection = BrokenConnection()
    monkeypatch.setattr(module, "_DB_PATH", str(tmp_path / "historical.sqlite"))
    monkeypatch.setattr(module.sqlite3, "connect", lambda *_args, **_kwargs: connection)

    with pytest.raises(sqlite3.OperationalError, match="journal setup failure"):
        with module._conn():
            pytest.fail("failed connection setup must not yield")

    assert connection.closed is True


@pytest.mark.parametrize("statement", ["PRAGMA journal_mode=WAL", "PRAGMA busy_timeout=30000"])
def test_monitoring_connection_closes_when_setup_fails(tmp_path, monkeypatch, statement):
    from backend.services import monitoring_storage as module

    class BrokenConnection:
        closed = False

        def execute(self, sql):
            if sql == statement:
                raise sqlite3.OperationalError("simulated monitoring setup failure")

        def rollback(self):
            pass

        def close(self):
            self.closed = True

    connection = BrokenConnection()
    monkeypatch.setattr(module.sqlite3, "connect", lambda *_args, **_kwargs: connection)

    with pytest.raises(sqlite3.OperationalError, match="monitoring setup failure"):
        with module._connect(tmp_path / "monitoring.sqlite"):
            pytest.fail("failed connection setup must not yield")

    assert connection.closed is True


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
