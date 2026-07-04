# -*- coding: utf-8 -*-
"""Tests for portfolio_store name/tags/note 留存字段升级。"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

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
