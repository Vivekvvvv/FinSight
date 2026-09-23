# -*- coding: utf-8 -*-
import importlib


def _module():
    return importlib.import_module("backend.graph.nodes.confirmation_gate")


def test_confirmation_gate_skip_mode_bypasses_interrupt(monkeypatch):
    module = _module()

    def _unexpected_interrupt(payload):  # pragma: no cover - should never run
        raise AssertionError("interrupt should not be called when confirmation_mode=skip")

    monkeypatch.setattr(module, "interrupt", _unexpected_interrupt)
    out = module.confirmation_gate(
        {
            "output_mode": "investment_report",
            "confirmation_mode": "skip",
        }
    )
    assert out.get("confirmation_intent") == "confirm_execute"
    assert out.get("confirmation_instruction") is None


def test_confirmation_gate_required_mode_forces_interrupt_and_confirm(monkeypatch):
    module = _module()
    captured: dict = {}

    def _fake_interrupt(payload):
        captured.update(payload)
        return payload["options"][0]

    monkeypatch.setattr(module, "interrupt", _fake_interrupt)
    out = module.confirmation_gate(
        {
            "query": "Generate AAPL report",
            "output_mode": "brief",
            "confirmation_mode": "required",
            "confirmation_options": ["Confirm execute", "Adjust parameters", "Cancel execution"],
            "plan_ir": {"rationale": "test plan", "required_agents": ["news_agent"]},
        }
    )
    assert out.get("user_confirmation") == "Confirm execute"
    assert out.get("confirmation_intent") == "confirm_execute"
    assert out.get("confirmation_instruction") is None
    assert "query" not in out
    assert out.get("require_confirmation") is False
    assert captured.get("required_agents") == ["news_agent"]


def test_confirmation_gate_adjust_instruction_rewrites_query(monkeypatch):
    module = _module()

    def _fake_interrupt(_payload):
        return "Adjust parameters: focus on fundamentals and valuation"

    monkeypatch.setattr(module, "interrupt", _fake_interrupt)
    out = module.confirmation_gate(
        {
            "query": "Generate AAPL investment report",
            "output_mode": "investment_report",
            "confirmation_mode": "required",
            "confirmation_options": ["Confirm execute", "Adjust parameters", "Cancel execution"],
        }
    )

    assert out.get("confirmation_intent") == "adjust_parameters"
    assert out.get("confirmation_instruction") == "focus on fundamentals and valuation"
    assert "[User adjustment] focus on fundamentals and valuation" in (out.get("query") or "")


def test_confirmation_gate_custom_free_text_treated_as_adjust(monkeypatch):
    module = _module()

    def _fake_interrupt(_payload):
        return "focus on free cash flow trend only"

    monkeypatch.setattr(module, "interrupt", _fake_interrupt)
    out = module.confirmation_gate(
        {
            "query": "Generate AAPL investment report",
            "output_mode": "investment_report",
            "confirmation_mode": "required",
        }
    )

    assert out.get("confirmation_intent") == "adjust_parameters"
    assert out.get("confirmation_instruction") == "focus on free cash flow trend only"
    assert "[User adjustment] focus on free cash flow trend only" in (out.get("query") or "")


def test_confirmation_gate_cancel_option_sets_cancel_intent(monkeypatch):
    module = _module()

    def _fake_interrupt(payload):
        return payload["options"][2]

    monkeypatch.setattr(module, "interrupt", _fake_interrupt)
    out = module.confirmation_gate(
        {
            "query": "Generate AAPL investment report",
            "output_mode": "investment_report",
            "confirmation_mode": "required",
            "confirmation_options": ["Confirm execute", "Adjust parameters", "Cancel execution"],
        }
    )

    assert out.get("confirmation_intent") == "cancel_execution"
    assert out.get("confirmation_instruction") is None


def test_confirmation_gate_explicit_require_false_has_highest_priority(monkeypatch):
    module = _module()

    def _unexpected_interrupt(payload):  # pragma: no cover - should never run
        raise AssertionError("interrupt should not be called when require_confirmation=False")

    monkeypatch.setattr(module, "interrupt", _unexpected_interrupt)
    out = module.confirmation_gate(
        {
            "output_mode": "investment_report",
            "confirmation_mode": "required",
            "require_confirmation": False,
        }
    )
    assert out.get("confirmation_intent") == "confirm_execute"


def test_confirmation_gate_invalid_mode_falls_back_to_auto(monkeypatch):
    module = _module()

    def _fake_interrupt(payload):
        return payload["options"][0]

    monkeypatch.setattr(module, "interrupt", _fake_interrupt)
    out = module.confirmation_gate(
        {
            "output_mode": "investment_report",
            "confirmation_mode": "invalid_mode",
            "confirmation_options": ["Confirm execute", "Adjust parameters", "Cancel execution"],
        }
    )
    assert out.get("confirmation_mode") == "auto"
    assert out.get("confirmation_intent") == "confirm_execute"


def test_parse_confirmation_response_negated_confirm_does_not_confirm():
    """R32: '我不确认/还没确认' 含 '确认' 子串但语义是否定，
    判成 confirm_execute 会在用户没同意时放行执行——安全方向最危险。"""
    from backend.graph.nodes.confirmation_gate import _INTENT_ADJUST, _parse_confirmation_response

    for text in ("我不确认这个数据", "还没确认好", "先不确认", "我能不能确认",
                 "I cannot confirm this", "don't approve"):
        intent, _ = _parse_confirmation_response(text, option_intents={})
        assert intent == _INTENT_ADJUST, text


def test_parse_confirmation_response_negated_cancel_does_not_cancel():
    """R32: '请不要取消'/'don't cancel' 语义是别取消，裸子串误杀执行。"""
    from backend.graph.nodes.confirmation_gate import _INTENT_CANCEL, _parse_confirmation_response

    for text in ("请不要取消", "先别取消", "don't cancel", "do not abort"):
        intent, _ = _parse_confirmation_response(text, option_intents={})
        assert intent != _INTENT_CANCEL, text


def test_parse_confirmation_response_plain_intents_still_work():
    """R32 正例：无否定的确认/取消与 '没问题，确认' 这类肯定短语不受影响。"""
    from backend.graph.nodes.confirmation_gate import (
        _INTENT_CANCEL,
        _INTENT_CONFIRM,
        _parse_confirmation_response,
    )

    for text in ("确认", "继续", "没问题，确认", "confirm", "ok continue"):
        intent, _ = _parse_confirmation_response(text, option_intents={})
        assert intent == _INTENT_CONFIRM, text
    for text in ("取消", "stop", "abort it", "终止执行"):
        intent, _ = _parse_confirmation_response(text, option_intents={})
        assert intent == _INTENT_CANCEL, text
