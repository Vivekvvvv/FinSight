# -*- coding: utf-8 -*-

import asyncio
import logging
from datetime import datetime

from backend.agents.base_agent import AgentOutput, EvidenceItem
from backend.orchestration.plan import PlanBuilder, PlanExecutor


class DummyAgent:
    def __init__(self, name: str):
        self.name = name

    async def research(self, query: str, ticker: str):
        return AgentOutput(
            agent_name=self.name,
            summary=f"{self.name} summary",
            evidence=[EvidenceItem(text="evidence", source="dummy")],
            confidence=0.9,
            data_sources=["dummy"],
            as_of=datetime.now().isoformat(),
            fallback_used=False,
            risks=[],
        )


class FailingAgent:
    async def research(self, query: str, ticker: str):
        raise RuntimeError("boom")


class FailingForum:
    async def synthesize(self, outputs, user_profile=None, context_summary=None):
        raise RuntimeError("PRIVATE_FORUM_CONNECTION_DETAIL")


class DummyForum:
    async def synthesize(self, outputs, user_profile=None):
        return {"consensus": "ok", "confidence": 0.8}


def test_plan_executor_runs_steps():
    agents = {"price": DummyAgent("price"), "news": DummyAgent("news")}
    plan = PlanBuilder.build_report_plan("query", "AAPL", list(agents.keys()))
    executor = PlanExecutor(agents, DummyForum())

    result = asyncio.run(executor.execute(plan, "query", "AAPL"))

    assert set(result["agent_outputs"].keys()) == {"price", "news"}
    assert result["plan"]["steps"][0]["status"] in {"completed", "failed"}
    assert any(event["event"] == "step_start" for event in result["trace"])


def test_plan_executor_returns_structured_error_details_for_partial_failure():
    agents = {"price": FailingAgent(), "technical": DummyAgent("technical")}
    plan = PlanBuilder.build_report_plan("query", "AAPL", list(agents.keys()))
    executor = PlanExecutor(agents, DummyForum())

    result = asyncio.run(executor.execute(plan, "query", "AAPL"))

    assert result["agent_outputs"] == {}
    assert result["errors"] == ["price:RuntimeError", "technical:dependency_failed"]
    assert result["error_details"] == [
        {
            "step_id": "collect_price",
            "agent": "price",
            "status": "failed",
            "error": "price:RuntimeError",
        },
        {
            "step_id": "collect_technical",
            "agent": "technical",
            "status": "skipped",
            "error": "technical:dependency_failed",
        },
    ]


def test_plan_executor_logs_when_event_channel_breaks(caplog):
    """回调抛错时事件被整条丢弃：trace 内部照记、最终 errors 也正确，但前端
    进度面板会停在中途（项目规则 2）。断链必须留可定位的 warning。
    """
    agents = {"price": DummyAgent("price")}
    plan = PlanBuilder.build_report_plan("query", "AAPL", list(agents.keys()))
    executor = PlanExecutor(agents, DummyForum())

    def _broken_listener(_record):
        raise RuntimeError("PRIVATE_EVENT_LISTENER_DETAIL")

    caplog.set_level(logging.WARNING, logger="backend.orchestration.plan")
    result = asyncio.run(executor.execute(plan, "query", "AAPL", on_event=_broken_listener))

    assert any(event["event"] == "step_done" for event in result["trace"])
    assert "[PlanExecutor] event emit failed" in caplog.text
    assert "PRIVATE_EVENT_LISTENER_DETAIL" not in caplog.text


def test_plan_executor_logs_skipped_coroutine_event_listener(caplog):
    """协程式回调会被 iscoroutinefunction 分支直接跳过：事件永远发不出去，
    调用方必须能在日志里看到这件事，而不是以为进度已在推送。"""

    async def _async_listener(_record):
        return None

    agents = {"price": DummyAgent("price")}
    plan = PlanBuilder.build_report_plan("query", "AAPL", list(agents.keys()))
    executor = PlanExecutor(agents, DummyForum())

    caplog.set_level(logging.WARNING, logger="backend.orchestration.plan")
    result = asyncio.run(executor.execute(plan, "query", "AAPL", on_event=_async_listener))

    assert any(event["event"] == "step_done" for event in result["trace"])
    assert "[PlanExecutor] coroutine event listener skipped" in caplog.text


def test_plan_executor_logs_broken_agent_event_channel(caplog):
    """agent 内部事件走 _emit_agent_event 转发，回调炸掉同样不能静默。"""
    captured: list = []

    class _ToolishAgent(DummyAgent):
        async def research(self, query, ticker, on_event=None):
            if on_event:
                on_event({"event": "agent_internal", "details": {}})
            return await super().research(query, ticker)

    agents = {"price": _ToolishAgent("price")}
    plan = PlanBuilder.build_report_plan("query", "AAPL", list(agents.keys()))
    executor = PlanExecutor(agents, DummyForum())

    def _broken_listener(_record):
        captured.append(_record)
        raise RuntimeError("PRIVATE_AGENT_EVENT_DETAIL")

    caplog.set_level(logging.WARNING, logger="backend.orchestration.plan")
    result = asyncio.run(executor.execute(plan, "query", "AAPL", on_event=_broken_listener))

    assert captured  # agent 确实把内部事件转发了出去（至少 step_start）
    assert "[PlanExecutor] agent event emit failed" in caplog.text
    assert "PRIVATE_AGENT_EVENT_DETAIL" not in caplog.text
    assert any(event["event"] == "step_done" for event in result["trace"])


def test_plan_executor_redacts_agent_error_from_result_and_trace(caplog):
    sentinel = "PRIVATE_AGENT_CONNECTION_DETAIL"

    class _PrivateFailingAgent:
        async def research(self, query: str, ticker: str):
            raise RuntimeError(sentinel)

    agents = {"price": _PrivateFailingAgent(), "technical": DummyAgent("technical")}
    plan = PlanBuilder.build_report_plan("query", "AAPL", list(agents.keys()))
    executor = PlanExecutor(agents, DummyForum())
    caplog.set_level(logging.DEBUG, logger="backend.orchestration.plan")

    result = asyncio.run(executor.execute(plan, "query", "AAPL"))

    assert sentinel not in str(result)
    assert sentinel not in caplog.text
    assert result["errors"][0] == "price:RuntimeError"
    assert any((event.get("details") or {}).get("error") == "RuntimeError" for event in result["trace"])


def test_plan_executor_redacts_forum_error_from_result_trace_and_logs(caplog):
    agents = {
        "price": DummyAgent("price"),
        "news": DummyAgent("news"),
        "macro": DummyAgent("macro"),
    }
    plan = PlanBuilder.build_report_plan("query", "AAPL", list(agents.keys()))
    executor = PlanExecutor(agents, FailingForum())
    caplog.set_level(logging.DEBUG, logger="backend.orchestration.plan")

    result = asyncio.run(executor.execute(plan, "query", "AAPL"))

    sentinel = "PRIVATE_FORUM_CONNECTION_DETAIL"
    assert sentinel not in str(result)
    assert sentinel not in caplog.text
    assert "RuntimeError" in result["errors"]
    assert any((event.get("details") or {}).get("error") == "RuntimeError" for event in result["trace"])
