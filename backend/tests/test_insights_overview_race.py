# -*- coding: utf-8 -*-
"""R102 回归：并发 generate 期间共享的 OverviewScorer._sub_scores 跨 symbol 污染。

InsightsOrchestrator 是模块级单例，_generate_fresh 在信号量内可并发 3 路：
symbol A 在 `self._overview.set_sub_scores(A)` 后于 digest 的 LLM await 处挂起，
symbol B 此时 `set_sub_scores(B)` 覆盖同一实例的 _sub_scores。A 恢复后
_parse_response → _deterministic_fallback_details 读到的是 B 的分数，
A 的 overview 卡片按 B 的子分折半，再按 A 缓存 TTL_INSIGHTS。
"""
from __future__ import annotations

import asyncio
import json


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_concurrent_overview_does_not_cross_sub_scores(monkeypatch):
    from backend.dashboard import scorers as scorer_mod
    from backend.dashboard.cache import DashboardCache
    from backend.dashboard.insights_engine import InsightsOrchestrator
    from backend.dashboard.schemas import InsightCard

    # A 四个维度全 9，B 全 1：确定性回退分差距必须 >3 才能观测折半污染。
    dim_score = {"AAA": 9.0, "BBB": 1.0}

    async def _fake_dim_digest(self, symbol, data):
        return InsightCard(
            agent_name="d",
            scorer_name="d_scorer",
            tab="t",
            score=dim_score[symbol],
            score_label="L",
            summary="s",
        )

    monkeypatch.setattr(scorer_mod.TechnicalScorer, "digest", _fake_dim_digest)
    monkeypatch.setattr(scorer_mod.FinancialScorer, "digest", _fake_dim_digest)
    monkeypatch.setattr(scorer_mod.NewsScorer, "digest", _fake_dim_digest)
    monkeypatch.setattr(scorer_mod.PeersScorer, "digest", _fake_dim_digest)

    # overview 走 LLM 路径；_call_llm 是挂起点——先到的（必为 A）挂起，
    # B 进入后一起放行，保证 B 的 set_sub_scores 在 A 恢复前已覆盖共享实例。
    a_inside = asyncio.Event()
    b_inside = asyncio.Event()

    monkeypatch.setattr(scorer_mod, "_get_llm", lambda: object())

    async def _blocking_overview_call(self, llm, prompt):
        if not a_inside.is_set():
            a_inside.set()
        else:
            b_inside.set()
        await asyncio.wait_for(b_inside.wait(), timeout=10)
        return json.dumps(
            {
                "score": 9.0,
                "score_label": "强势",
                "summary": "s",
                "key_points": [],
                "risks": [],
            }
        )

    monkeypatch.setattr(
        scorer_mod.OverviewScorer, "_call_llm", _blocking_overview_call
    )

    orch = InsightsOrchestrator(cache=DashboardCache())
    monkeypatch.setattr(orch, "_fetch_technicals", lambda symbol: {})
    monkeypatch.setattr(orch, "_fetch_news", lambda symbol: {})

    async def _main():
        task_a = asyncio.create_task(orch.generate("AAA"))
        await asyncio.wait_for(a_inside.wait(), timeout=10)
        task_b = asyncio.create_task(orch.generate("BBB"))
        return await asyncio.wait_for(asyncio.gather(task_a, task_b), timeout=15)

    resp_a, _resp_b = _run(_main())

    # A 的维度分全 9：LLM 9 与确定性回退 ~9 一致 → overview 应保持 9。
    # 若 A 读到 B 的 _sub_scores（全 1），回退 ~1，|9-1|>3 → 被折半成 5。
    assert resp_a.insights["overview"].score == 9.0
