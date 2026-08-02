# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pytest

from backend.graph import checkpointer as checkpointer_mod


def _reset_bundle() -> None:
    checkpointer_mod.reset_checkpointer_caches()


def test_checkpointer_sqlite_persistent(tmp_path, monkeypatch):
    sqlite_file = tmp_path / "checkpoints.sqlite"
    monkeypatch.setenv("LANGGRAPH_CHECKPOINTER_BACKEND", "sqlite")
    monkeypatch.setenv("LANGGRAPH_CHECKPOINT_SQLITE_PATH", str(sqlite_file))
    monkeypatch.setenv("LANGGRAPH_CHECKPOINTER_ALLOW_MEMORY_FALLBACK", "true")
    _reset_bundle()
    try:
        info = checkpointer_mod.get_graph_checkpointer_info()
        assert info["backend"] == "sqlite"
        assert info["persistent"] is True
        assert Path(info["location"]).name == "checkpoints.sqlite"
    finally:
        _reset_bundle()


def test_async_checkpointer_sqlite_persistent(tmp_path, monkeypatch):
    sqlite_file = tmp_path / "async-checkpoints.sqlite"
    monkeypatch.setenv("LANGGRAPH_CHECKPOINTER_BACKEND", "sqlite")
    monkeypatch.setenv("LANGGRAPH_CHECKPOINT_SQLITE_PATH", str(sqlite_file))
    monkeypatch.setenv("LANGGRAPH_CHECKPOINTER_ALLOW_MEMORY_FALLBACK", "true")
    _reset_bundle()
    try:
        bundle = asyncio.run(checkpointer_mod.aget_checkpointer_bundle())
        assert bundle.info.backend == "sqlite"
        assert bundle.info.persistent is True
        info = checkpointer_mod.get_graph_checkpointer_info()
        assert Path(info["location"]).name == "async-checkpoints.sqlite"
    finally:
        _reset_bundle()


def test_checkpointer_fallback_to_memory(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_CHECKPOINTER_BACKEND", "unknown-backend")
    monkeypatch.setenv("LANGGRAPH_CHECKPOINTER_ALLOW_MEMORY_FALLBACK", "true")
    _reset_bundle()
    try:
        info = checkpointer_mod.get_graph_checkpointer_info()
        assert info["backend"] == "memory"
        assert info["persistent"] is False
        assert info["fallback_used"] is True
        assert isinstance(info["fallback_reason"], str) and info["fallback_reason"]
    finally:
        _reset_bundle()


def test_checkpointer_no_fallback_raises(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_CHECKPOINTER_BACKEND", "unknown-backend")
    monkeypatch.setenv("LANGGRAPH_CHECKPOINTER_ALLOW_MEMORY_FALLBACK", "false")
    _reset_bundle()
    try:
        with pytest.raises(ValueError):
            checkpointer_mod.get_checkpointer_bundle()
    finally:
        _reset_bundle()


def test_checkpointer_postgres_requires_dsn(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_CHECKPOINTER_BACKEND", "postgres")
    monkeypatch.delenv("LANGGRAPH_CHECKPOINT_POSTGRES_DSN", raising=False)
    monkeypatch.setenv("LANGGRAPH_CHECKPOINTER_ALLOW_MEMORY_FALLBACK", "false")
    _reset_bundle()
    try:
        with pytest.raises(ValueError, match="LANGGRAPH_CHECKPOINT_POSTGRES_DSN"):
            checkpointer_mod.get_checkpointer_bundle()
    finally:
        _reset_bundle()


def test_async_checkpointer_close_error_log_is_redacted(caplog):
    class FailingAsyncContext:
        @staticmethod
        async def __aexit__(*_args):
            raise RuntimeError("private async checkpointer detail")

    bundle = checkpointer_mod._memory_bundle(reason=None, fallback_used=False)
    bundle._async_cm = FailingAsyncContext()

    with caplog.at_level(logging.ERROR, logger="backend.graph.checkpointer"):
        asyncio.run(bundle.aclose())

    assert bundle._async_cm is None
    assert "private async checkpointer detail" not in caplog.text
    assert "failed to close async checkpointer context" in caplog.text


def test_async_bundle_sync_stack_close_error_log_is_redacted(caplog):
    class FailingStack:
        @staticmethod
        def close():
            raise RuntimeError("private sync stack detail")

    bundle = checkpointer_mod._memory_bundle(reason=None, fallback_used=False)
    bundle._stack = FailingStack()

    with caplog.at_level(logging.ERROR, logger="backend.graph.checkpointer"):
        asyncio.run(bundle.aclose())

    assert bundle._stack is None
    assert "private sync stack detail" not in caplog.text
    assert "failed to close sync checkpointer stack asynchronously" in caplog.text


def test_sync_bundle_stack_close_error_log_is_redacted(caplog):
    class FailingStack:
        @staticmethod
        def close():
            raise RuntimeError("private sync close detail")

    bundle = checkpointer_mod._memory_bundle(reason=None, fallback_used=False)
    bundle._stack = FailingStack()

    with caplog.at_level(logging.ERROR, logger="backend.graph.checkpointer"):
        bundle.close()

    assert bundle._stack is None
    assert "private sync close detail" not in caplog.text
    assert "failed to close sync checkpointer stack" in caplog.text


def test_stale_async_bundle_close_error_log_is_redacted(monkeypatch, caplog):
    class FailingBundle:
        @staticmethod
        async def aclose():
            raise RuntimeError("private stale bundle detail")

    replacement = checkpointer_mod._memory_bundle(reason=None, fallback_used=False)

    async def build_replacement():
        return replacement

    monkeypatch.setattr(checkpointer_mod, "_async_bundle", FailingBundle())
    monkeypatch.setattr(checkpointer_mod, "_async_bundle_loop_id", -1)
    monkeypatch.setattr(checkpointer_mod, "_async_lock", None)
    monkeypatch.setattr(checkpointer_mod, "_build_async_bundle", build_replacement)

    with caplog.at_level(logging.ERROR, logger="backend.graph.checkpointer"):
        resolved = asyncio.run(checkpointer_mod.aget_checkpointer_bundle())

    assert resolved is replacement
    assert "private stale bundle detail" not in caplog.text
    assert "failed to close stale async checkpointer bundle" in caplog.text
    checkpointer_mod._async_bundle = None
    checkpointer_mod._async_lock = None
    checkpointer_mod._async_bundle_loop_id = None


def test_async_cache_reset_close_error_log_is_redacted(monkeypatch, caplog):
    class FailingBundle:
        @staticmethod
        async def aclose():
            raise RuntimeError("private async reset detail")

    _reset_bundle()
    monkeypatch.setattr(checkpointer_mod, "_async_bundle", FailingBundle())
    with caplog.at_level(logging.ERROR, logger="backend.graph.checkpointer"):
        asyncio.run(checkpointer_mod.areset_checkpointer_caches())

    assert checkpointer_mod._async_bundle is None
    assert "private async reset detail" not in caplog.text
    assert "failed to close async bundle" in caplog.text


def test_async_checkpointer_fallback_log_is_redacted(monkeypatch, caplog):
    async def fail_sqlite(_sqlite_path):
        raise RuntimeError("private async backend detail")

    monkeypatch.setenv("LANGGRAPH_CHECKPOINTER_BACKEND", "sqlite")
    monkeypatch.setenv("LANGGRAPH_CHECKPOINTER_ALLOW_MEMORY_FALLBACK", "true")
    monkeypatch.setattr(checkpointer_mod, "_create_async_sqlite_bundle", fail_sqlite)

    with caplog.at_level(logging.WARNING, logger="backend.graph.checkpointer"):
        bundle = asyncio.run(checkpointer_mod._build_async_bundle())

    assert bundle.info.backend == "memory"
    assert bundle.info.fallback_used is True
    assert bundle.info.fallback_reason == "RuntimeError"
    assert "private async backend detail" not in str(bundle.info.fallback_reason)
    assert "private async backend detail" not in caplog.text
    assert "LangGraph async checkpointer fallback to memory" in caplog.text


def test_sync_checkpointer_fallback_reason_and_log_are_redacted(monkeypatch, caplog):
    def fail_sqlite(_sqlite_path):
        raise RuntimeError("private sync backend detail")

    monkeypatch.setenv("LANGGRAPH_CHECKPOINTER_BACKEND", "sqlite")
    monkeypatch.setenv("LANGGRAPH_CHECKPOINTER_ALLOW_MEMORY_FALLBACK", "true")
    monkeypatch.setattr(checkpointer_mod, "_create_sync_sqlite_bundle", fail_sqlite)

    with caplog.at_level(logging.WARNING, logger="backend.graph.checkpointer"):
        bundle = checkpointer_mod._build_sync_bundle()

    assert bundle.info.backend == "memory"
    assert bundle.info.fallback_used is True
    assert bundle.info.fallback_reason == "RuntimeError"
    assert "private sync backend detail" not in caplog.text
    assert "LangGraph sync checkpointer fallback to memory" in caplog.text
