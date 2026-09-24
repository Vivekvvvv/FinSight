# -*- coding: utf-8 -*-
import asyncio


def _run(coro):
    return asyncio.run(coro)


def test_r98_aget_graph_runner_survives_loop_change(monkeypatch):
    """aget_graph_runner 用 _graph_runner_loop_id 支持"换 loop 重建 runner"，
    但互斥用的 _graph_runner_lock 只在首次创建。asyncio.Lock 在首次
    "等待"时绑定当时的 loop——此后第二个事件循环上的竞争者走等待路径
    时 _get_loop 直接抛 RuntimeError（bound to a different event loop），
    多 loop 重建路径必崩（无竞争的 acquire 不查 loop，故必须人为制造
    两次竞争才能复现：loop A 上靠一次 acquire() 等待把锁绑到 A——
    同 loop 的 aget_graph_runner 会 early-return 不碰锁；loop B 上
    主协程持旧锁，逼 task 内的 aget_graph_runner 走等待路径）。"""
    import importlib

    from langgraph.checkpoint.memory import MemorySaver

    runner_module = importlib.import_module("backend.graph.runner")
    runner_module.reset_graph_runner()

    async def _fake_checkpointer():
        return MemorySaver()

    monkeypatch.setattr(runner_module, "aget_graph_checkpointer", _fake_checkpointer)

    async def _bind_lock_to_loop_a():
        first = await runner_module.aget_graph_runner()
        lock = runner_module._graph_runner_lock
        await lock.acquire()
        # 制造一次锁等待：等待路径调用 _get_loop，把锁绑到本 loop
        waiter = asyncio.create_task(lock.acquire())
        await asyncio.sleep(0.05)
        lock.release()
        await waiter  # waiter 拿到锁
        lock.release()
        return first

    async def _rebuild_on_loop_b():
        old_lock = runner_module._graph_runner_lock
        await old_lock.acquire()  # 空锁走快速路径，不查 _loop
        try:
            # 竞争 → 等待路径 → _get_loop 发现锁绑在旧 loop → buggy 抛 RuntimeError
            task = asyncio.create_task(runner_module.aget_graph_runner())
            await asyncio.sleep(0.05)
        finally:
            old_lock.release()
        return await task  # buggy: RuntimeError 传播

    # 保持 loop 引用（id() 复用会让"换 loop"判定失真）
    loop_a = asyncio.new_event_loop()
    loop_b = asyncio.new_event_loop()
    try:
        first = loop_a.run_until_complete(_bind_lock_to_loop_a())
        assert first is not None
        lock_a = runner_module._graph_runner_lock

        second = loop_b.run_until_complete(_rebuild_on_loop_b())
        assert second is not None
        assert second is not first  # 换了 loop → 重建 runner
        assert runner_module._graph_runner_lock is not lock_a
    finally:
        runner_module.reset_graph_runner()
        loop_a.close()
        loop_b.close()


def test_r105_aget_checkpointer_bundle_survives_loop_change(monkeypatch):
    """aget_checkpointer_bundle 用 _async_bundle_loop_id 支持"换 loop 重建
    bundle"（注释明说是为 tests/reloads 的多 loop 路径设计），但互斥用的
    _async_lock 只在首次创建——asyncio.Lock 首次"等待"时绑定当时 loop，
    换 loop 后竞争者走等待路径抛 RuntimeError(bound to a different
    event loop)。锁必须与 bundle 一样随 loop 更换，复现手法同 R98。"""
    import importlib

    cp_module = importlib.import_module("backend.graph.checkpointer")
    monkeypatch.setenv("LANGGRAPH_CHECKPOINTER_BACKEND", "memory")

    async def _bind_lock_to_loop_a():
        first = await cp_module.aget_checkpointer_bundle()
        lock = cp_module._async_lock
        await lock.acquire()
        # 制造一次锁等待：等待路径调用 _get_loop，把锁绑到本 loop
        waiter = asyncio.create_task(lock.acquire())
        await asyncio.sleep(0.05)
        lock.release()
        await waiter  # waiter 拿到锁
        lock.release()
        return first

    async def _rebuild_on_loop_b():
        old_lock = cp_module._async_lock
        await old_lock.acquire()  # 空锁走快速路径，不查 _loop
        try:
            # 竞争 → 等待路径 → _get_loop 发现锁绑在旧 loop → buggy 抛 RuntimeError
            task = asyncio.create_task(cp_module.aget_checkpointer_bundle())
            await asyncio.sleep(0.05)
        finally:
            old_lock.release()
        return await task  # buggy: RuntimeError 传播

    # 保持 loop 引用（id() 复用会让"换 loop"判定失真）
    loop_a = asyncio.new_event_loop()
    loop_b = asyncio.new_event_loop()
    try:
        first = loop_a.run_until_complete(_bind_lock_to_loop_a())
        assert first is not None
        lock_a = cp_module._async_lock

        second = loop_b.run_until_complete(_rebuild_on_loop_b())
        assert second is not None
        assert second is not first  # 换了 loop → 重建 bundle
        assert cp_module._async_lock is not lock_a
    finally:
        cp_module._async_bundle = None
        cp_module._async_lock = None
        cp_module._async_bundle_loop_id = None
        loop_a.close()
        loop_b.close()


def test_langgraph_runner_import_and_invoke():
    from backend.graph import GraphRunner

    runner = GraphRunner.create()
    result = _run(runner.ainvoke(thread_id="t-basic", query="分析 AAPL", ui_context={"active_symbol": "AAPL"}))

    assert isinstance(result, dict)
    assert "artifacts" in result
    assert "draft_markdown" in result["artifacts"]
    assert "policy" in result

    trace = result.get("trace") or {}
    spans = trace.get("spans") or []
    assert [s.get("node") for s in spans] == [
        "build_initial_state",
        "reset_turn_state",
        "trim_history",
        "summarize_history",
        "normalize_ui_context",
        "decide_output_mode",
        "chat_respond",
        "resolve_subject",
        "clarify",
        "parse_operation",
        "policy_gate",
        "planner",
        "confirmation_gate",
        "execute_plan",
        "synthesize",
        "render",
    ]


def test_resolve_subject_selection_priority_and_dedupe():
    from backend.graph import GraphRunner

    runner = GraphRunner.create()
    ui_context = {
        "active_symbol": "AAPL",
        "selections": [
            {"type": "news", "id": "n1", "title": "t1"},
            {"type": "news", "id": "n1", "title": "t1-dup"},
        ],
    }
    result = _run(runner.ainvoke(thread_id="t-sel", query="分析影响", ui_context=ui_context))

    subject = result.get("subject") or {}
    assert subject.get("subject_type") == "news_item"
    assert subject.get("selection_ids") == ["n1"]


def test_resolve_subject_filing_and_doc_selection_types():
    from backend.graph import GraphRunner

    runner = GraphRunner.create()

    filing = _run(
        runner.ainvoke(
            thread_id="t-filing",
            query="总结要点",
            ui_context={"selections": [{"type": "filing", "id": "f1", "title": "10-K"}]},
        )
    )
    assert (filing.get("subject") or {}).get("subject_type") == "filing"

    doc = _run(
        runner.ainvoke(
            thread_id="t-doc",
            query="总结要点",
            ui_context={"selections": [{"type": "doc", "id": "d1", "title": "research"}]},
        )
    )
    assert (doc.get("subject") or {}).get("subject_type") == "research_doc"

    # Legacy: report -> doc
    legacy = _run(
        runner.ainvoke(
            thread_id="t-legacy-report",
            query="总结要点",
            ui_context={"selections": [{"type": "report", "id": "r1", "title": "legacy"}]},
        )
    )
    subject = legacy.get("subject") or {}
    assert subject.get("subject_type") == "research_doc"
    assert subject.get("selection_types") == ["doc"]


def test_resolve_subject_active_symbol_fallback():
    from backend.graph import GraphRunner

    runner = GraphRunner.create()
    result = _run(runner.ainvoke(thread_id="t-symbol", query="分析苹果", ui_context={"active_symbol": "aapl"}))

    subject = result.get("subject") or {}
    assert subject.get("subject_type") == "company"
    assert subject.get("tickers") == ["AAPL"]


def test_resolve_subject_query_ticker_overrides_active_symbol():
    from backend.graph import GraphRunner

    runner = GraphRunner.create()
    # active_symbol can be stale UI state; query ticker should win.
    result = _run(
        runner.ainvoke(thread_id="t-override", query="NVDA 最新股价和技术面分析", ui_context={"active_symbol": "GOOGL"})
    )

    subject = result.get("subject") or {}
    assert subject.get("subject_type") == "company"
    assert subject.get("tickers") == ["NVDA"]


def test_decide_output_mode_ui_override_and_safe_default():
    from backend.graph import GraphRunner

    runner = GraphRunner.create()

    # UI override wins
    result = _run(
        runner.ainvoke(
            thread_id="t-mode",
            query="分析影响",
            ui_context={"active_symbol": "AAPL"},
            output_mode="investment_report",
        )
    )
    assert result.get("output_mode") == "investment_report"

    # Generic analysis should NOT imply investment_report
    result2 = _run(runner.ainvoke(thread_id="t-mode2", query="分析一下", ui_context={}))
    assert result2.get("output_mode") == "brief"
