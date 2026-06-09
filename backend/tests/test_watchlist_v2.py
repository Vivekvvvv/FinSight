# -*- coding: utf-8 -*-
"""Tests for Watchlist 2.0 metadata (name / tags / note)."""

from __future__ import annotations

import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


@pytest.fixture
def memory_service(tmp_path):
    from backend.services.memory import MemoryService

    return MemoryService(storage_path=str(tmp_path))


def test_add_with_metadata(memory_service):
    ok = memory_service.add_to_watchlist(
        "user_a", "AAPL", name="Apple Inc.", tags=["tech", "long"], note="anchor",
    )
    assert ok is True
    items = memory_service.list_watchlist_items("user_a")
    assert len(items) == 1
    item = items[0]
    assert item["ticker"] == "AAPL"
    assert item["name"] == "Apple Inc."
    assert item["tags"] == ["tech", "long"]
    assert item["note"] == "anchor"
    assert item["added_at"]
    assert item["updated_at"]


def test_add_without_metadata_backwards_compat(memory_service):
    """Old call sites pass only (user_id, ticker) — must still work."""
    ok = memory_service.add_to_watchlist("user_b", "MSFT")
    assert ok is True
    profile = memory_service.get_user_profile("user_b")
    assert "MSFT" in profile.watchlist
    items = memory_service.list_watchlist_items("user_b")
    assert items[0]["name"] is None
    assert items[0]["tags"] == []


def test_update_meta_only(memory_service):
    memory_service.add_to_watchlist("user_c", "TSLA")
    ok = memory_service.update_watchlist_meta(
        "user_c", "TSLA", name="Tesla", tags=["ev"], note="quarterly review",
    )
    assert ok is True
    items = memory_service.list_watchlist_items("user_c")
    assert items[0]["name"] == "Tesla"
    assert items[0]["tags"] == ["ev"]
    assert items[0]["note"] == "quarterly review"


def test_update_meta_fails_when_ticker_missing(memory_service):
    ok = memory_service.update_watchlist_meta("user_d", "GOOG", name="Google")
    assert ok is False


def test_partial_update_keeps_existing_fields(memory_service):
    memory_service.add_to_watchlist(
        "user_e", "NVDA", name="Nvidia", tags=["ai"], note="gpu leader",
    )
    # Partial update — only name; tags/note must remain.
    memory_service.update_watchlist_meta("user_e", "NVDA", name="NVIDIA Corp.")
    item = memory_service.list_watchlist_items("user_e")[0]
    assert item["name"] == "NVIDIA Corp."
    assert item["tags"] == ["ai"]
    assert item["note"] == "gpu leader"


def test_remove_clears_metadata(memory_service):
    memory_service.add_to_watchlist("user_f", "AMD", name="AMD", tags=["chip"])
    memory_service.remove_from_watchlist("user_f", "AMD")
    profile = memory_service.get_user_profile("user_f")
    assert "AMD" not in profile.watchlist
    assert "AMD" not in (profile.watchlist_meta or {})
    items = memory_service.list_watchlist_items("user_f")
    assert items == []


def test_ticker_normalized_uppercase(memory_service):
    memory_service.add_to_watchlist("user_g", "googl", name="Alphabet")
    profile = memory_service.get_user_profile("user_g")
    assert "GOOGL" in profile.watchlist
    items = memory_service.list_watchlist_items("user_g")
    assert items[0]["ticker"] == "GOOGL"
    assert items[0]["name"] == "Alphabet"


def test_legacy_profile_with_no_meta_field_loads_cleanly(memory_service, tmp_path):
    """Reading an existing profile JSON without watchlist_meta field still works."""
    import json
    user_id = "legacy_user"
    file_path = tmp_path / f"{user_id}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "user_id": user_id,
                "risk_tolerance": "high",
                "watchlist": ["IBM", "ORCL"],
                # NOTE: no watchlist_meta field at all
            },
            f,
        )
    items = memory_service.list_watchlist_items(user_id)
    assert {item["ticker"] for item in items} == {"IBM", "ORCL"}
    for item in items:
        assert item["name"] is None
        assert item["tags"] == []


def test_q_filter_hits(memory_service):
    """q= filter matches by ticker substring (case-insensitive)."""
    memory_service.add_to_watchlist("user_q1", "AAPL", name="Apple Inc.")
    memory_service.add_to_watchlist("user_q1", "TSLA", name="Tesla")
    items = memory_service.list_watchlist_items("user_q1")
    q = "aap"
    filtered = [it for it in items if q in it.get("ticker", "").lower() or q in (it.get("name") or "").lower()]
    assert len(filtered) == 1
    assert filtered[0]["ticker"] == "AAPL"


def test_q_filter_no_results(memory_service):
    """q= filter returns empty list when nothing matches."""
    memory_service.add_to_watchlist("user_q2", "MSFT", name="Microsoft")
    items = memory_service.list_watchlist_items("user_q2")
    q = "zzznomatch"
    filtered = [it for it in items if q in it.get("ticker", "").lower() or q in (it.get("name") or "").lower()]
    assert filtered == []
