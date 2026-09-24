# -*- coding: utf-8 -*-
"""insights_engine 的 asyncio 对象跨事件循环残留守卫。

checkpointer.py / runner.py 已修过同族缺陷（asyncio.Lock 首次等待时绑定
当时的 loop，换 loop 后竞争者走等待路径恒 RuntimeError；两文件注释原文
记录了同一缺陷描述），insights_engine 的模块级 semaphore 与
_refresh_tasks 残留任务是同族漏网站点。
"""

import asyncio
from types import SimpleNamespace

import pytest

from backend.dashboard import insights_engine


def _reset_semaphore() -> None:
    insights_engine._generation_semaphore = None


def test_generation_semaphore_is_rebound_per_event_loop():
    """_get_semaphore 只查 is None——首次竞争 acquire 将实例绑到当时的 loop；
    换 loop（测试多 TestClient / 进程内重建循环）后任何竞争 acquire 恒
    RuntimeError(bound to a different event loop)，且永不重建。应按 loop 重建。"""

    async def _contend():
        sem = insights_engine._get_semaphore()
        # 耗尽全部许可制造竞争，让等待路径的 _get_loop() 绑定当前 loop
        for _ in range(insights_engine._MAX_CONCURRENT_SYMBOLS):
            await sem.acquire()
        waiter = asyncio.create_task(sem.acquire())
        await asyncio.sleep(0)  # 让 waiter 走到 _get_loop()
        for _ in range(insights_engine._MAX_CONCURRENT_SYMBOLS):
            sem.release()
        await asyncio.wait_for(waiter, timeout=2)
        return sem

    _reset_semaphore()
    try:
        asyncio.run(_contend())  # loop A：竞争路径绑定 loop A 后随 run 关闭
        # 不重置——旧实现返回绑死 loop A 的实例，竞争 acquire 恒 RuntimeError
        asyncio.run(_contend())  # loop B：不应抛 RuntimeError
    finally:
        _reset_semaphore()


def test_semaphore_reused_within_same_loop():
    """同一 loop 内必须复用同一实例（限流语义依赖共享计数器）。"""

    async def _both():
        return insights_engine._get_semaphore(), insights_engine._get_semaphore()

    _reset_semaphore()
    try:
        first, second = asyncio.run(_both())
        assert first is second
    finally:
        _reset_semaphore()


def test_stale_refresh_task_from_dead_loop_does_not_block_reschedule():
    """loop 关闭时挂起的 Task 留在 _refresh_tasks——done() 恒 False，
    _schedule_background_refresh 恒早退，该 symbol 永久不再刷新。
    非本 loop 的任务不得再拦截调度。"""

    async def _pending() -> None:
        await asyncio.sleep(3600)

    dead_loop = asyncio.new_event_loop()
    dead_task = dead_loop.create_task(_pending())
    dead_loop.close()  # 任务永远 pending：done() 恒 False
    dead_task.get_coro().close()  # 关闭底层协程避免 never-awaited 告警
    insights_engine._refresh_tasks["ZZTEST"] = dead_task

    async def _noop(symbol: str) -> None:
        return None

    async def _schedule():
        stub = SimpleNamespace(_refresh_in_background=_noop)
        insights_engine.InsightsOrchestrator._schedule_background_refresh(stub, "ZZTEST")

    try:
        asyncio.run(_schedule())
        new_task = insights_engine._refresh_tasks.get("ZZTEST")
        assert new_task is not None
        assert new_task is not dead_task
    finally:
        insights_engine._refresh_tasks.pop("ZZTEST", None)
