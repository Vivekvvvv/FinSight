from types import SimpleNamespace

import pytest

from backend.orchestration.budget import BudgetManager, BudgetExceededError, BudgetedTools


def test_budget_tool_calls():
    budget = BudgetManager(max_tool_calls=1, max_rounds=10, max_seconds=60)
    budget.consume_tool_call("tool_a")
    with pytest.raises(BudgetExceededError):
        budget.consume_tool_call("tool_b")


def test_budget_rounds():
    budget = BudgetManager(max_tool_calls=10, max_rounds=1, max_seconds=60)
    budget.consume_round("r1")
    with pytest.raises(BudgetExceededError):
        budget.consume_round("r2")


def test_budgeted_tools_wraps_callable_and_counts_calls():
    budget = BudgetManager(max_tool_calls=2, max_rounds=10, max_seconds=60)
    tools = BudgetedTools(SimpleNamespace(echo=lambda value: value), budget)

    assert tools.echo("ok") == "ok"
    assert budget.tool_calls == 1
    assert budget.events[-1]["name"] == "echo"


def test_budgeted_tools_missing_tool_error_names_tool():
    budget = BudgetManager(max_tool_calls=2, max_rounds=10, max_seconds=60)
    tools = BudgetedTools(SimpleNamespace(), budget)

    with pytest.raises(AttributeError, match="missing_tool"):
        _ = tools.missing_tool
