import pytest

from backend.services.task_generator import TaskContext, TaskGenerator


def test_empty_task_limits_do_not_return_unbounded_or_tail_results():
    from backend.services.task_generator import AITask
    tasks = [AITask(id=str(i), title="test", category="news") for i in range(3)]
    assert TaskGenerator()._deduplicate_and_rank(tasks, max_tasks=0) == []
    assert TaskGenerator()._deduplicate_and_rank(tasks, max_tasks=-1) == []


@pytest.mark.asyncio
async def test_duplicate_or_invalid_holdings_do_not_trigger_three_stock_rebalance():
    for rows in ([{"ticker": "AAPL", "shares": 1}] * 3,
                 [{"ticker": "AAPL", "shares": 1}, {"ticker": None}, {"ticker": "BAD", "error": "bad"}]):
        tasks = await TaskGenerator().generate(TaskContext(portfolio=rows))
        assert all(task.category != "rebalance" for task in tasks)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [{"success": False}, {"error": "bad"}, {"status": " Failed "}])
async def test_failed_position_records_do_not_generate_research_tasks(failure):
    tasks = await TaskGenerator().generate(TaskContext(portfolio=[{"ticker": "AAPL", "shares": 1, **failure}]))
    assert [task.category for task in tasks] == ["news"]


@pytest.mark.asyncio
@pytest.mark.parametrize("ticker", [None, True, 123, [], {}])
async def test_task_generation_skips_nontext_position_instruments(ticker):
    tasks = await TaskGenerator().generate(TaskContext(portfolio=[{"ticker": ticker, "shares": 1}]))
    assert [task.category for task in tasks] == ["news"]


@pytest.mark.asyncio
@pytest.mark.parametrize("report_id", [None, True, 123, [], " "])
async def test_readable_task_report_requires_a_text_identifier(report_id):
    tasks = await TaskGenerator().generate(TaskContext(
        portfolio=[{"ticker": "AAPL", "shares": 1}],
        recent_reports={"AAPL": {"report_id": report_id, "age_days": 1}}))
    assert all(task.category != "review" for task in tasks)


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["ticker", "symbol"])
async def test_task_report_instrument_mismatch_does_not_offer_wrong_report(field):
    tasks = await TaskGenerator().generate(TaskContext(
        portfolio=[{"ticker": "AAPL", "shares": 1}],
        recent_reports={"AAPL": {"report_id": "wrong", "age_days": 1, field: "MSFT"}}))
    assert all(task.category != "review" for task in tasks)
    assert any(task.category == "generate" for task in tasks)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [{"success": False}, {"error": "bad"}, {"status": " Failed "}])
async def test_failed_report_metadata_cannot_create_readable_report_tasks(failure):
    tasks = await TaskGenerator().generate(TaskContext(
        portfolio=[{"ticker": "AAPL", "shares": 1}],
        recent_reports={"AAPL": {"report_id": "bad", "age_days": 1, **failure}}))
    assert all(task.category != "review" for task in tasks)
    assert any(task.category == "generate" for task in tasks)


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["ticker", "symbol"])
async def test_price_anomaly_requires_matching_snapshot_instrument(field):
    tasks = await TaskGenerator().generate(TaskContext(
        portfolio=[{"ticker": "AAPL", "shares": 1}],
        snapshots={"AAPL": {"change_pct": -10, field: "MSFT"}}))
    assert all(task.category != "anomaly" for task in tasks)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [{"success": False}, {"error": "bad"}, {"status": " Failed "}])
async def test_failed_snapshots_do_not_create_price_anomaly_tasks(failure):
    tasks = await TaskGenerator().generate(TaskContext(
        portfolio=[{"ticker": "AAPL", "shares": 1}],
        snapshots={"AAPL": {"change_pct": -10, **failure}}))
    assert all(task.category != "anomaly" for task in tasks)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [True, float("-inf"), float("nan"), "bad", [], {}, -101])
async def test_invalid_snapshot_change_does_not_break_tasks_or_fabricate_anomalies(change):
    tasks = await TaskGenerator().generate(TaskContext(
        portfolio=[{"ticker": "AAPL", "shares": 1}],
        snapshots={"AAPL": {"change_percent": change}},
    ))

    assert all(task.category != "anomaly" for task in tasks)
    assert any(task.category == "generate" for task in tasks)


@pytest.mark.asyncio
async def test_numeric_change_alias_recovers_from_an_invalid_primary():
    tasks = await TaskGenerator().generate(TaskContext(
        portfolio=[{"ticker": "AAPL", "shares": 1}],
        snapshots={"AAPL": {"change_percent": "bad", "change_pct": "-4.5"}},
    ))

    anomaly = next(task for task in tasks if task.category == "anomaly")
    assert "-4.5%" in anomaly.reason


@pytest.mark.asyncio
@pytest.mark.parametrize("age", [None, "bad", float("nan"), float("inf"), True, -1, 3, "4"])
async def test_unavailable_or_stale_report_age_does_not_create_valid_review(age):
    context = TaskContext(
        portfolio=[{"ticker": "AAPL", "shares": 1}],
        recent_reports={"AAPL": {"report_id": "r1", "age_days": age}},
    )

    tasks = await TaskGenerator().generate(context)

    assert all(task.category != "review" for task in tasks)
    assert any(task.category == "reanalyze" for task in tasks)


@pytest.mark.asyncio
async def test_known_recent_report_remains_readable():
    tasks = await TaskGenerator().generate(TaskContext(
        portfolio=[{"ticker": "AAPL", "shares": 1}],
        recent_reports={"AAPL": {"report_id": "r1", "age_days": 2}},
    ))

    assert any(task.category == "review" and task.status == "done" for task in tasks)
    assert all(task.category != "reanalyze" for task in tasks)
