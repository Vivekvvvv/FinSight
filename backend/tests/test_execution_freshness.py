# -*- coding: utf-8 -*-
import importlib


def _freshness(monkeypatch, *, demo: str | None = None, live: str | None = None) -> dict:
    monkeypatch.delenv("FINSIGHT_DEMO_MODE", raising=False)
    monkeypatch.delenv("LANGGRAPH_EXECUTE_LIVE_TOOLS", raising=False)
    if demo is not None:
        monkeypatch.setenv("FINSIGHT_DEMO_MODE", demo)
    if live is not None:
        monkeypatch.setenv("LANGGRAPH_EXECUTE_LIVE_TOOLS", live)
    module = importlib.import_module("backend.services.execution_helpers")
    return module._resolve_freshness_meta()


def test_freshness_defaults_to_fallback_when_live_tools_disabled(monkeypatch):
    assert _freshness(monkeypatch) == {
        "freshness_status": "fallback",
        "fallback_level": 1,
        "freshness_reason": "tool_dry_run",
    }


def test_freshness_is_live_when_live_tools_enabled(monkeypatch):
    assert _freshness(monkeypatch, live="true") == {
        "freshness_status": "live",
        "fallback_level": 0,
        "freshness_reason": "live_tools",
    }


def test_freshness_demo_mode_overrides_live_tools(monkeypatch):
    assert _freshness(monkeypatch, demo="true", live="true") == {
        "freshness_status": "demo",
        "fallback_level": 2,
        "freshness_reason": "demo_mode",
    }
