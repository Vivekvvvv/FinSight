# -*- coding: utf-8 -*-
"""
PlanBuilder fast-path tests.
"""

from backend.orchestration.plan import PlanBuilder


def test_plan_builder_fast_path_skips_forum():
    plan = PlanBuilder.build_report_plan("price check", "AAPL", ["price"])
    assert plan.steps
    assert all(step.step_type != "forum" for step in plan.steps)


def test_plan_builder_adds_forum_for_multi_agents():
    plan = PlanBuilder.build_report_plan(
        "analyze Tesla", "TSLA", ["price", "news", "technical"]
    )
    assert any(step.step_type == "forum" for step in plan.steps)


def test_plan_builder_reads_timeout_env_overrides(monkeypatch):
    monkeypatch.setenv("FINSIGHT_AGENT_TIMEOUT_PRICE", "7")
    monkeypatch.setenv("FINSIGHT_AGENT_TIMEOUT_FORUM", "11")

    plan = PlanBuilder.build_report_plan(
        "analyze Tesla", "TSLA", ["price", "news", "technical"]
    )

    price_step = next(step for step in plan.steps if step.agent_name == "price")
    forum_step = next(step for step in plan.steps if step.step_type == "forum")

    assert price_step.timeout_seconds == 7
    assert forum_step.timeout_seconds == 11
