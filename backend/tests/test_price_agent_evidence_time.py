# -*- coding: utf-8 -*-
"""R64：PriceAgent 失败分支不得把取数时刻伪造成数据时间。

``_format_output`` 在 ``raw_data`` 为空（所有数据源都失败）时返回
``summary="价格数据获取失败"``、``source="unknown"``，但 evidence 的
``timestamp`` 用的是 ``datetime.now()``——下游把它当成“这条行情是刚刚
更新的”，一次彻底失败的取数看起来和实时报价一样新鲜。
"""
from __future__ import annotations

from unittest.mock import MagicMock

from backend.agents.price_agent import PriceAgent


def _agent() -> PriceAgent:
    return PriceAgent(None, MagicMock(), MagicMock())


def test_failed_fetch_does_not_fabricate_evidence_timestamp():
    output = _agent()._format_output("价格数据获取失败", None)

    assert output.evidence, "失败也要留下一条证据说明没有数据"
    item = output.evidence[0]
    assert item.source == "unknown"
    assert item.timestamp is None
    assert any("获取失败" in e.text or "暂无数据" in e.text for e in output.evidence)


def test_failed_fetch_with_options_keeps_option_as_of_none():
    agent = _agent()
    agent._last_option_metrics = {"iv_atm": 0.3, "put_call_ratio_oi": 1.1, "source": "yfinance_options"}

    output = agent._format_output("价格数据获取失败", None)

    option_items = [e for e in output.evidence if e.source == "yfinance_options"]
    assert option_items
    # as_of=None 时旧代码 str(None) 产出字面量 "None"，会被当成有效时间串。
    assert option_items[0].timestamp is None


def test_successful_quote_still_carries_timestamp():
    output = _agent()._format_output(
        "", {"ticker": "AAPL", "price": 100.0, "source": "yfinance", "as_of": "2026-10-16T20:00:00Z"}
    )

    assert output.evidence[0].timestamp == "2026-10-16T20:00:00Z"
