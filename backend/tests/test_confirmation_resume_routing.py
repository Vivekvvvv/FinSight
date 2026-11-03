# -*- coding: utf-8 -*-
import asyncio

import pytest


def _run(coro):
    return asyncio.run(coro)


async def _resume_and_collect_final_state(runner, *, thread_id: str, resume_value):
    final_state = {}
    async for event in runner.resume(thread_id=thread_id, resume_value=resume_value):
        if event.get("event") == "on_chain_end":
            output = (event.get("data") or {}).get("output")
            if isinstance(output, dict):
                final_state = output
    return final_state


def test_confirmation_resume_adjust_replans_once(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_PLANNER_MODE", "stub")

    from backend.graph import GraphRunner

    thread_id = "t-confirm-adjust"
    runner = GraphRunner.create()

    initial = _run(
        runner.ainvoke(
            thread_id=thread_id,
            query="Generate AAPL investment report",
            ui_context={"active_symbol": "AAPL"},
            output_mode="investment_report",
            confirmation_mode="required",
        )
    )
    assert initial.get("__interrupt__"), "first pass should be interrupted by confirmation gate"

    final = _run(
        _resume_and_collect_final_state(
            runner,
            thread_id=thread_id,
            resume_value="Adjust parameters: focus on fundamentals",
        )
    )

    assert "[User adjustment] focus on fundamentals" in str(final.get("query") or "")
    spans = [s.get("node") for s in ((final.get("trace") or {}).get("spans") or [])]
    assert spans.count("planner") >= 2, "adjust flow should route back to planner"
    assert "execute_plan" not in spans, "调整参数不能直接放行重规划后的计划"
    assert _run(runner._graph.aget_state({"configurable": {"thread_id": thread_id}})).next == ("confirmation_gate",)

    confirmed = _run(_resume_and_collect_final_state(
        runner, thread_id=thread_id, resume_value="Confirm execute",
    ))
    confirmed_spans = [s.get("node") for s in ((confirmed.get("trace") or {}).get("spans") or [])]
    assert confirmed_spans.count("planner") == spans.count("planner")
    assert "execute_plan" in confirmed_spans


def test_confirmation_resume_confirm_executes_without_replanning(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_PLANNER_MODE", "stub")

    from backend.graph import GraphRunner

    thread_id = "t-confirm-continue"
    runner = GraphRunner.create()

    initial = _run(
        runner.ainvoke(
            thread_id=thread_id,
            query="Generate TSLA investment report",
            ui_context={"active_symbol": "TSLA"},
            output_mode="investment_report",
            confirmation_mode="required",
        )
    )
    assert initial.get("__interrupt__"), "first pass should be interrupted by confirmation gate"

    final = _run(
        _resume_and_collect_final_state(
            runner,
            thread_id=thread_id,
            resume_value="Confirm execute",
        )
    )

    assert "[User adjustment]" not in str(final.get("query") or "")
    spans = [s.get("node") for s in ((final.get("trace") or {}).get("spans") or [])]
    assert spans.count("planner") == 1, "confirm flow should continue directly without replanning"


@pytest.mark.parametrize("responses", [
    ("",), (None,), ("调整参数",), ("我不确认这个数据",), ("don't approve",),
    ("", "调整参数", None),
])
def test_non_approval_responses_keep_real_checkpoint_paused_until_confirmation(monkeypatch, responses):
    from backend.graph import GraphRunner

    thread_id = "t-confirm-stay-paused"
    runner = GraphRunner.create()
    initial = _run(runner.ainvoke(
        thread_id=thread_id, query="Generate AAPL investment report",
        ui_context={"active_symbol": "AAPL"}, output_mode="investment_report",
        confirmation_mode="required",
    ))
    assert initial.get("__interrupt__")

    for response in responses:
        _run(_resume_and_collect_final_state(runner, thread_id=thread_id, resume_value=response))
        snapshot = _run(runner._graph.aget_state({"configurable": {"thread_id": thread_id}}))
        assert snapshot.next == ("confirmation_gate",), "没有明确批准时必须继续暂停"
        spans = [s.get("node") for s in ((snapshot.values.get("trace") or {}).get("spans") or [])]
        assert "execute_plan" not in spans

    final = _run(_resume_and_collect_final_state(
        runner, thread_id=thread_id, resume_value="Confirm execute",
    ))
    spans = [s.get("node") for s in ((final.get("trace") or {}).get("spans") or [])]
    assert "execute_plan" in spans


def test_reprompted_confirmation_can_still_be_cancelled():
    from backend.graph import GraphRunner

    thread_id = "t-confirm-reprompt-cancel"
    runner = GraphRunner.create()
    initial = _run(runner.ainvoke(
        thread_id=thread_id, query="Generate AAPL investment report",
        ui_context={"active_symbol": "AAPL"}, output_mode="investment_report",
        confirmation_mode="required",
    ))
    assert initial.get("__interrupt__")
    _run(_resume_and_collect_final_state(runner, thread_id=thread_id, resume_value=""))
    final = _run(_resume_and_collect_final_state(runner, thread_id=thread_id, resume_value="Cancel execution"))

    assert final["confirmation_intent"] == "cancel_execution"
    assert _run(runner._graph.aget_state({"configurable": {"thread_id": thread_id}})).next == ()
    spans = [s.get("node") for s in ((final.get("trace") or {}).get("spans") or [])]
    assert "execute_plan" not in spans
