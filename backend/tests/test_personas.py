# -*- coding: utf-8 -*-
"""Tests for the Persona Mode subsystem.

Covers:
  - YAML loading + Pydantic schema validation
  - get_persona() fallback behavior
  - AgentWeights clamp (0.2 floor, 3.0 ceiling)
  - build_initial_state populates persona_id + persona_config
  - policy_gate._apply_persona_weights re-ranks scores
  - synthesize._format_persona_lens injects lens block
"""
from __future__ import annotations

import importlib

import pytest

from backend.personas import get_persona, list_personas, load_personas
from backend.personas.registry import AgentWeights, Persona


# ---------------------------------------------------------------------------
# Registry / loader
# ---------------------------------------------------------------------------


def test_load_personas_returns_all_four_builtin():
    registry = load_personas(force_reload=True)
    assert "neutral" in registry
    assert "value_investor" in registry
    assert "macro_hedge" in registry
    assert "momentum_trader" in registry
    assert isinstance(registry["value_investor"], Persona)


def test_get_persona_neutral_fallback_for_missing_id():
    persona = get_persona("nonexistent_persona_xyz")
    assert persona.id == "neutral"


def test_get_persona_handles_none_and_empty():
    assert get_persona(None).id == "neutral"
    assert get_persona("").id == "neutral"
    assert get_persona("   ").id == "neutral"


def test_list_personas_starts_with_neutral():
    items = list_personas()
    assert items, "expected at least one persona"
    assert items[0].id == "neutral", "neutral must come first for stable UI ordering"


def test_value_investor_has_lens_and_weights():
    p = get_persona("value_investor")
    assert p.synthesis_lens.strip(), "value_investor must have a non-empty lens"
    # Fundamentals weighted up, technical weighted down
    assert p.agent_weights.fundamental > 1.0
    assert p.agent_weights.technical < 1.0


# ---------------------------------------------------------------------------
# AgentWeights clamping
# ---------------------------------------------------------------------------


def test_agent_weights_clamps_below_floor():
    w = AgentWeights(fundamental=0.0, macro=-5.0)
    assert w.fundamental >= 0.2
    assert w.macro >= 0.2


def test_agent_weights_clamps_above_ceiling():
    w = AgentWeights(news=99.0)
    assert w.news <= 3.0


def test_agent_weights_get_lookup_handles_agent_suffix():
    w = AgentWeights(fundamental=1.5)
    assert w.get("fundamental") == pytest.approx(1.5)
    assert w.get("fundamental_agent") == pytest.approx(1.5)
    assert w.get("unknown_thing", 0.7) == pytest.approx(0.7)


# ---------------------------------------------------------------------------
# build_initial_state integration
# ---------------------------------------------------------------------------


def _patch_memory_loader(monkeypatch, module):
    monkeypatch.setattr(module, "load_memory_context", lambda thread_id: None)


def test_build_initial_state_populates_persona_from_ui_context(monkeypatch):
    module = importlib.import_module("backend.graph.nodes.build_initial_state")
    _patch_memory_loader(monkeypatch, module)

    updates = module.build_initial_state(
        {
            "thread_id": "public:anonymous:t1",
            "query": "分析 AAPL",
            "ui_context": {"persona_id": "value_investor"},
        }
    )

    assert updates["persona_id"] == "value_investor"
    cfg = updates["persona_config"]
    assert isinstance(cfg, dict)
    assert cfg["id"] == "value_investor"
    assert cfg.get("synthesis_lens"), "lens must be carried in persona_config"


def test_build_initial_state_falls_back_to_neutral_when_persona_missing(monkeypatch):
    module = importlib.import_module("backend.graph.nodes.build_initial_state")
    _patch_memory_loader(monkeypatch, module)

    updates = module.build_initial_state(
        {"thread_id": "public:anonymous:t2", "query": "分析 AAPL", "ui_context": {}}
    )

    assert updates["persona_id"] == "neutral"
    assert updates["persona_config"]["id"] == "neutral"


def test_build_initial_state_ignores_unknown_persona(monkeypatch):
    module = importlib.import_module("backend.graph.nodes.build_initial_state")
    _patch_memory_loader(monkeypatch, module)

    updates = module.build_initial_state(
        {
            "thread_id": "public:anonymous:t3",
            "query": "分析 AAPL",
            "ui_context": {"persona_id": "unknown_xyz"},
        }
    )

    assert updates["persona_id"] == "neutral", "unknown ids must downgrade to neutral"


def test_build_initial_state_explicit_persona_id_takes_precedence(monkeypatch):
    """If both state.persona_id and ui_context.persona_id are set, state wins."""
    module = importlib.import_module("backend.graph.nodes.build_initial_state")
    _patch_memory_loader(monkeypatch, module)

    updates = module.build_initial_state(
        {
            "thread_id": "public:anonymous:t4",
            "query": "分析 AAPL",
            "persona_id": "macro_hedge",
            "ui_context": {"persona_id": "value_investor"},
        }
    )

    assert updates["persona_id"] == "macro_hedge"


# ---------------------------------------------------------------------------
# policy_gate weight application
# ---------------------------------------------------------------------------


def test_apply_persona_weights_reranks_scores():
    from backend.graph.nodes.policy_gate import _apply_persona_weights

    persona = get_persona("value_investor").model_dump()
    selection = {
        "selected": ["technical_agent", "fundamental_agent", "news_agent"],
        "required": [],
        "scores": {
            "technical_agent": 0.9,
            "fundamental_agent": 0.6,
            "news_agent": 0.7,
        },
    }
    out = _apply_persona_weights(selection, persona)

    new_scores = out["scores"]
    # value_investor: fundamental ↑ (1.5), technical ↓ (0.3), news ↓ (0.5)
    assert new_scores["fundamental_agent"] > new_scores["technical_agent"]
    assert "persona_weights_applied" in out
    # Selected list reordered: fundamental should now come before technical
    assert out["selected"].index("fundamental_agent") < out["selected"].index("technical_agent")


def test_apply_persona_weights_neutral_is_noop():
    from backend.graph.nodes.policy_gate import _apply_persona_weights

    neutral = get_persona("neutral").model_dump()
    selection = {
        "selected": ["technical_agent", "fundamental_agent"],
        "required": [],
        "scores": {"technical_agent": 0.9, "fundamental_agent": 0.6},
    }
    out = _apply_persona_weights(selection, neutral)
    # Neutral weights = all 1.0 → no skew flag, scores unchanged
    assert "persona_weights_applied" not in out


def test_apply_persona_weights_handles_missing_inputs():
    from backend.graph.nodes.policy_gate import _apply_persona_weights

    selection = {"selected": ["a"], "scores": {"a": 0.5}}
    # Persona config missing → no-op
    assert _apply_persona_weights(selection, None) == selection
    # Scores missing → no-op
    assert _apply_persona_weights({"selected": ["a"]}, {"agent_weights": {}}) == {"selected": ["a"]}


def test_apply_persona_weights_preserves_required_agents_order():
    from backend.graph.nodes.policy_gate import _apply_persona_weights

    persona = get_persona("momentum_trader").model_dump()
    selection = {
        "selected": ["fundamental_agent", "technical_agent", "news_agent"],
        "required": ["fundamental_agent"],  # required is pinned even if downweighted
        "scores": {"fundamental_agent": 0.8, "technical_agent": 0.5, "news_agent": 0.5},
    }
    out = _apply_persona_weights(selection, persona)
    # Required agent stays first regardless of low weight (0.3)
    assert out["selected"][0] == "fundamental_agent"


# ---------------------------------------------------------------------------
# synthesize lens injection
# ---------------------------------------------------------------------------


def test_format_persona_lens_returns_block_for_value_investor():
    from backend.graph.nodes.synthesize import _format_persona_lens

    state = {"persona_config": get_persona("value_investor").model_dump()}
    lens = _format_persona_lens(state)
    assert "<persona_lens>" in lens
    assert "价值投资者" in lens
    assert "诚实优先级" in lens, "honesty-first reminder must be present"


def test_format_persona_lens_returns_empty_for_neutral():
    from backend.graph.nodes.synthesize import _format_persona_lens

    state = {"persona_config": get_persona("neutral").model_dump()}
    lens = _format_persona_lens(state)
    assert lens == "", "neutral persona must not inject any lens block (BC guarantee)"


def test_format_persona_lens_handles_missing_state_field():
    from backend.graph.nodes.synthesize import _format_persona_lens

    assert _format_persona_lens({}) == ""
    assert _format_persona_lens({"persona_config": None}) == ""
    assert _format_persona_lens({"persona_config": {"synthesis_lens": ""}}) == ""
