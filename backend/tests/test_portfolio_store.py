# -*- coding: utf-8 -*-
"""Tests for portfolio_store name/tags/note 留存字段升级。"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _setup_tmp_db(tmp_path: Path, monkeypatch):
    """Redirect portfolio_store to a per-test sqlite file."""
    monkeypatch.setenv("FINSIGHT_DATA_DIR", str(tmp_path))
    from backend.services import portfolio_store

    importlib.reload(portfolio_store)
    return portfolio_store


def test_update_position_persists_name_tags_note(tmp_path, monkeypatch):
    store = _setup_tmp_db(tmp_path, monkeypatch)

    store.update_position(
        "test_session",
        "AAPL",
        10,
        avg_cost=150.0,
        name="Apple Core",
        tags=["tech", "long"],
        note="anchor position",
    )
    rows = store.get_positions("test_session")
    assert len(rows) == 1
    row = rows[0]
    assert row["ticker"] == "AAPL"
    assert row["shares"] == 10
    assert row["avg_cost"] == 150.0
    assert row["name"] == "Apple Core"
    assert row["tags"] == ["tech", "long"]
    assert row["note"] == "anchor position"


def test_sync_positions_round_trip_tags(tmp_path, monkeypatch):
    store = _setup_tmp_db(tmp_path, monkeypatch)

    store.sync_positions(
        "sess",
        [
            {"ticker": "MSFT", "shares": 5, "avg_cost": 320, "name": "Cloud", "tags": ["ai"], "note": "watch dvd"},
            {"ticker": "GOOG", "shares": 2, "tags": ["ai", "ads"]},
        ],
    )
    rows = store.get_positions("sess")
    by_ticker = {r["ticker"]: r for r in rows}

    assert by_ticker["MSFT"]["name"] == "Cloud"
    assert by_ticker["MSFT"]["tags"] == ["ai"]
    assert by_ticker["MSFT"]["note"] == "watch dvd"
    assert by_ticker["GOOG"]["tags"] == ["ai", "ads"]
    assert by_ticker["GOOG"]["name"] is None


def test_portfolio_tags_are_bounded_on_write_and_legacy_read(tmp_path, monkeypatch):
    store = _setup_tmp_db(tmp_path, monkeypatch)
    store.update_position(
        "session",
        "AAPL",
        1,
        tags=[" ok ", 1, "x" * 100] + [f"tag-{index}" for index in range(30)],
    )
    position = store.get_positions("session")[0]
    assert position["tags"][0] == "ok"
    assert position["tags"][1] == "x" * 64
    assert len(position["tags"]) == 19

    with store._db_lock, store._connect() as connection:
        connection.execute(
            "UPDATE portfolio_positions SET tags_json = ? WHERE session_id = ?",
            ('{"tag": true}', "session"),
        )
    assert store.get_positions("session")[0]["tags"] == []


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), "bad"])
def test_update_position_rejects_invalid_numeric_values(tmp_path, monkeypatch, value):
    store = _setup_tmp_db(tmp_path, monkeypatch)

    with pytest.raises(ValueError):
        store.update_position("session", "AAPL", value)
    with pytest.raises(ValueError):
        store.update_position("session", "AAPL", 1, avg_cost=value)

    assert store.get_positions("session") == []


def test_sync_positions_rolls_back_on_invalid_numeric_value(tmp_path, monkeypatch):
    store = _setup_tmp_db(tmp_path, monkeypatch)
    store.update_position("session", "AAPL", 1, avg_cost=100)

    with pytest.raises(ValueError):
        store.sync_positions("session", [{"ticker": "MSFT", "shares": "nan"}])

    positions = store.get_positions("session")
    assert [(item["ticker"], item["shares"]) for item in positions] == [("AAPL", 1.0)]


@pytest.mark.parametrize("column", ["shares", "avg_cost"])
def test_get_positions_skips_legacy_non_finite_numeric_values(
    tmp_path, monkeypatch, caplog, column
):
    store = _setup_tmp_db(tmp_path, monkeypatch)
    store.update_position("session", "AAPL", 1, avg_cost=100)
    store.update_position("session", "MSFT", 2, avg_cost=200)
    with store._db_lock, store._connect() as connection:
        connection.execute(
            f"UPDATE portfolio_positions SET {column} = ? WHERE session_id = ? AND ticker = ?",
            (float("inf"), "session", "AAPL"),
        )

    positions = store.get_positions("session")

    assert [item["ticker"] for item in positions] == ["MSFT"]
    assert "Skipping invalid stored portfolio position" in caplog.text
    assert "Skipping invalid stored portfolio position" in caplog.text


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_save_suggestion_rejects_non_finite_json(tmp_path, monkeypatch, value):
    store = _setup_tmp_db(tmp_path, monkeypatch)

    with pytest.raises(ValueError):
        store.save_suggestion("suggestion", "session", {"weight": value})

    assert store.list_suggestions("session") == []


def test_list_suggestions_sanitizes_legacy_non_finite_json(tmp_path, monkeypatch, caplog):
    store = _setup_tmp_db(tmp_path, monkeypatch)
    store.save_suggestion("suggestion", "session", {"weight": 1})
    with store._db_lock, store._connect() as connection:
        connection.execute(
            "UPDATE rebalance_suggestions SET data = ? WHERE suggestion_id = ?",
            ('{"weight": NaN}', "suggestion"),
        )

    suggestions = store.list_suggestions("session")

    assert suggestions[0]["data"] == {}
    assert "stored rebalance suggestion parse failed" in caplog.text


def test_update_position_partial_keeps_existing_metadata(tmp_path, monkeypatch):
    store = _setup_tmp_db(tmp_path, monkeypatch)

    store.update_position(
        "s2",
        "TSLA",
        20,
        avg_cost=200,
        name="Tesla",
        tags=["ev"],
        note="quarterly review",
    )
    # 第二次 upsert 不传 name/tags/note 应该保留先前的值
    store.update_position("s2", "TSLA", 25, avg_cost=210)
    rows = store.get_positions("s2")
    assert rows[0]["shares"] == 25
    assert rows[0]["avg_cost"] == 210
    assert rows[0]["name"] == "Tesla"
    assert rows[0]["tags"] == ["ev"]
    assert rows[0]["note"] == "quarterly review"


def test_sync_positions_preserves_sector_currency_opened_at(tmp_path, monkeypatch):
    """全量同步 payload 不含 sector/currency/opened_at，已有值必须保留。"""
    store = _setup_tmp_db(tmp_path, monkeypatch)

    store.update_position(
        "s3",
        "NVDA",
        10,
        avg_cost=100,
        sector="Semiconductors",
        currency="USD",
        opened_at="2026-01-15",
    )
    store.update_position("s3", "0700.HK", 100, avg_cost=350, currency="HKD")

    # 同步 payload 只带基础字段（与 API 层 PortfolioPositionPayload 一致）
    store.sync_positions(
        "s3",
        [
            {"ticker": "NVDA", "shares": 12, "avg_cost": 105},
            {"ticker": "0700.HK", "shares": 100, "avg_cost": 350},
        ],
    )
    by_ticker = {r["ticker"]: r for r in store.get_positions("s3")}
    assert by_ticker["NVDA"]["sector"] == "Semiconductors"
    assert by_ticker["NVDA"]["currency"] == "USD"
    assert by_ticker["NVDA"]["opened_at"] == "2026-01-15"
    assert by_ticker["0700.HK"]["currency"] == "HKD"
    assert by_ticker["NVDA"]["shares"] == 12  # 基础字段仍按 payload 替换


def test_sync_positions_payload_overrides_preserved_columns(tmp_path, monkeypatch):
    """payload 若显式带 sector/currency/opened_at，则覆盖旧值；新 ticker 默认 USD。"""
    store = _setup_tmp_db(tmp_path, monkeypatch)

    store.update_position("s4", "AAPL", 5, sector="Hardware")
    store.sync_positions(
        "s4",
        [
            {"ticker": "AAPL", "shares": 6, "sector": "Consumer Tech"},
            {"ticker": "MSFT", "shares": 3},
        ],
    )
    by_ticker = {r["ticker"]: r for r in store.get_positions("s4")}
    assert by_ticker["AAPL"]["sector"] == "Consumer Tech"
    assert by_ticker["MSFT"]["sector"] is None
    assert by_ticker["MSFT"]["currency"] == "USD"


def test_get_all_active_sessions_parses_private_session_user_id(tmp_path, monkeypatch):
    """认证会话 "private:{user_id}:default" 必须解析出真实 user_id，
    其余格式回退 default_user（旧实现按 "_" 切分会产出 "private:default" 这类垃圾值，
    导致每日风险快照写入的 user_id 与查询侧永远对不上）。"""
    store = _setup_tmp_db(tmp_path, monkeypatch)

    store.update_position("private:alice:default", "AAPL", 1)
    store.update_position("private:default_user:default", "MSFT", 2)
    store.update_position("adhoc_dev_session", "NVDA", 3)

    mapping = dict(store.get_all_active_sessions())
    assert mapping["private:alice:default"] == "alice"
    assert mapping["private:default_user:default"] == "default_user"
    assert mapping["adhoc_dev_session"] == "default_user"


def test_corrupt_portfolio_json_is_logged_without_exposing_payload(
    tmp_path,
    monkeypatch,
    caplog,
):
    import logging

    store = _setup_tmp_db(tmp_path, monkeypatch)
    session_id = "private:test-user:default"
    store.update_position(session_id, "AAPL", 1, tags=["safe"])
    store.save_suggestion("suggestion-corrupt", session_id, {"safe": True})
    corrupt_payload = "{ PRIVATE_CORRUPT_JSON"
    with store._db_lock, store._connect() as conn:
        conn.execute(
            "UPDATE portfolio_positions SET tags_json = ? WHERE session_id = ? AND ticker = ?",
            (corrupt_payload, session_id, "AAPL"),
        )
        conn.execute(
            "UPDATE rebalance_suggestions SET data = ? WHERE suggestion_id = ?",
            (corrupt_payload, "suggestion-corrupt"),
        )
        conn.commit()

    caplog.set_level(logging.WARNING, logger="backend.services.portfolio_store")
    positions = store.get_positions(session_id)
    suggestions = store.list_suggestions(session_id)

    assert positions[0]["tags"] == []
    assert suggestions[0]["data"] == {}
    assert "stored portfolio tags parse failed" in caplog.text
    assert "stored rebalance suggestion parse failed" in caplog.text
    assert corrupt_payload not in caplog.text
