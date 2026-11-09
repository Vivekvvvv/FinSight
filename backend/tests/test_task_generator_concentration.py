import pytest

from backend.services.task_generator import TaskContext, TaskGenerator


@pytest.mark.asyncio
async def test_failed_position_lots_cannot_inflate_concentration_warnings():
    tasks = await TaskGenerator().generate(TaskContext(
        portfolio=[{"ticker": "BAD", "shares": 100, "error": "bad"},
                   {"ticker": "AAPL", "shares": 1}, {"ticker": "MSFT", "shares": 1}],
        snapshots={"BAD": {"price": 100}, "AAPL": {"price": 100}, "MSFT": {"price": 100}}))
    risk = next(task for task in tasks if task.category == "risk")
    assert "BAD" not in risk.reason and "50%" in risk.reason


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["ticker", "symbol"])
async def test_mismatched_concentration_snapshots_use_cost_estimates(field):
    tasks = await TaskGenerator().generate(TaskContext(
        portfolio=[{"ticker": "AAPL", "shares": 1, "avg_cost": 100},
                   {"ticker": "MSFT", "shares": 1, "avg_cost": 100}],
        snapshots={"AAPL": {"price": 900, field: "NVDA"}, "MSFT": {"price": 100}}))
    risk = next(task for task in tasks if task.category == "risk")
    assert "50%" in risk.reason and "成本价估算" in risk.reason


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [{"success": False}, {"error": "bad"}, {"status": " Failed "}])
async def test_failed_snapshots_use_cost_estimates_in_concentration(failure):
    tasks = await TaskGenerator().generate(TaskContext(
        portfolio=[{"ticker": "AAPL", "shares": 1, "avg_cost": 100},
                   {"ticker": "MSFT", "shares": 1, "avg_cost": 100}],
        snapshots={"AAPL": {"price": 900, **failure}, "MSFT": {"price": 100}}))
    risk = next(task for task in tasks if task.category == "risk")
    assert "50%" in risk.reason and "成本价估算" in risk.reason


@pytest.mark.asyncio
async def test_repeated_position_lots_do_not_overwrite_concentration_values():
    tasks = await TaskGenerator().generate(TaskContext(
        portfolio=[{"ticker": "AAPL", "shares": 5}, {"ticker": " aapl ", "shares": 5},
                   {"ticker": "MSFT", "shares": 9}],
        snapshots={"AAPL": {"price": 100}, "MSFT": {"price": 100}}))
    risk = next(task for task in tasks if task.category == "risk")
    assert "AAPL" in risk.reason and "53%" in risk.reason


@pytest.mark.asyncio
async def test_concentration_uses_market_value_not_shares():
    generator = TaskGenerator()
    context = TaskContext(
        portfolio=[
            {"ticker": "AAPL", "shares": 100, "avg_cost": 150},
            {"ticker": "NVDA", "shares": 100, "avg_cost": 700},
        ],
        snapshots={
            "AAPL": {"price": 150},
            "NVDA": {"price": 800},
        },
    )

    tasks = await generator.generate(context)
    concentration = next((task for task in tasks if task.category == "risk"), None)

    assert concentration is not None
    assert "NVDA" in concentration.reason
    assert "84%" in concentration.reason or "85%" in concentration.reason


@pytest.mark.asyncio
async def test_concentration_falls_back_to_cost_with_reason():
    generator = TaskGenerator()
    context = TaskContext(
        portfolio=[
            {"ticker": "AAPL", "shares": 100, "avg_cost": 200},
            {"ticker": "MSFT", "shares": 100, "avg_cost": 100},
        ],
        snapshots={},
    )

    tasks = await generator.generate(context)
    concentration = next((task for task in tasks if task.category == "risk"), None)

    assert concentration is not None
    assert "AAPL" in concentration.reason
    assert "成本价估算" in concentration.reason


@pytest.mark.asyncio
async def test_missing_position_valuation_does_not_create_false_full_concentration(caplog):
    context = TaskContext(
        portfolio=[{"ticker": "AAPL", "shares": 1}, {"ticker": "MSFT", "shares": 100}],
        snapshots={"AAPL": {"price": 100}},
    )

    tasks = await TaskGenerator().generate(context)

    assert all(task.category != "risk" for task in tasks)
    assert "concentration unavailable" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("shares, price", [(1e308, 100), (1, 1e308)])
async def test_overflowing_portfolio_valuation_cannot_hide_concentration(shares, price, caplog):
    tasks = await TaskGenerator().generate(TaskContext(
        portfolio=[{"ticker": "AAPL", "shares": shares}, {"ticker": "MSFT", "shares": shares}],
        snapshots={"AAPL": {"price": price}, "MSFT": {"price": price}},
    ))

    assert all(task.category != "risk" for task in tasks)
    assert "concentration unavailable" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("with_close", [False, True])
async def test_invalid_primary_price_does_not_hide_valid_valuation_fallback(with_close):
    context = TaskContext(
        portfolio=[{"ticker": "AAPL", "shares": 100, "avg_cost": 200},
            {"ticker": "MSFT", "shares": 100, "avg_cost": 20}],
        snapshots={"AAPL": {"price": -1, **({"close": 100} if with_close else {})},
            "MSFT": {"price": 20}},
    )

    tasks = await TaskGenerator().generate(context)
    risk = next((task for task in tasks if task.category == "risk"), None)
    assert risk is not None

    assert "AAPL" in risk.reason
    assert ("成本价估算" in risk.reason) is (not with_close)
    assert ("83%" if with_close else "91%") in risk.reason
