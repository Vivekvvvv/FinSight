# -*- coding: utf-8 -*-
"""R67 回归：morning brief 计数不把"有价无涨跌"（partial quote）算成横盘。

_synthesize_morning_brief_data 的 up/down/flat 此前用 `safe_float(...) or 0`，
缺 change_percent 的标的被折成 0 → 算横盘，虚增"横盘 N 只"并把 market_mood
拉向中性。改为只统计真正拿到涨跌幅的标的。返回结构外层是 {brief_data, ...}。
"""
from __future__ import annotations

from backend.graph.nodes.synthesize import _synthesize_morning_brief_data


def _brief(step_outputs: dict) -> dict:
    tickers = list(step_outputs.keys())
    steps = [
        {"id": f"s{i}", "name": "get_stock_price", "inputs": {"ticker": t}}
        for i, t in enumerate(tickers)
    ]
    step_results = {
        f"s{i}": {"output": step_outputs[t]} for i, t in enumerate(tickers)
    }
    state = {
        "subject": {"tickers": tickers},
        "plan_ir": {"steps": steps},
        "artifacts": {"step_results": step_results},
    }
    return _synthesize_morning_brief_data(state)["brief_data"]


def test_partial_quote_not_counted_as_flat():
    # AAA 上涨 2.0%；BBB 仅有价、无涨跌幅（partial quote）
    brief = _brief({
        "AAA": {"price": 100.0, "change": 2.0, "change_percent": 2.0},
        "BBB": {"price": 50.0},
    })
    # BBB 缺涨跌 → 不算横盘（旧代码会把 BBB 记成横盘 1）
    assert "上涨 1 只，下跌 0 只，横盘 0 只" in brief["summary"]
    # 情绪只按有效涨跌（+2.0%）→ bullish；旧代码把 BBB 当 0 拉平 avg=1.0 →
    # cautiously_optimistic
    assert brief["market_mood"] == "bullish"


def test_genuine_flat_still_counted():
    # 真平盘（0.0%）仍算横盘
    brief = _brief({
        "AAA": {"price": 100.0, "change": 0.0, "change_percent": 0.0},
    })
    assert "上涨 0 只，下跌 0 只，横盘 1 只" in brief["summary"]


def test_all_partial_quotes_mood_unknown():
    # 全部缺涨跌 → 没测到方向，不能报成"中性"（那是观测结论）
    brief = _brief({
        "AAA": {"price": 100.0},
        "BBB": {"price": 50.0},
    })
    assert brief["market_mood"] == "unknown"
    assert "上涨 0 只，下跌 0 只，横盘 0 只" in brief["summary"]
    assert "整体情绪：中性" not in brief["summary"]
    assert "暂不判断整体情绪" in brief["summary"]
    assert brief["action_items"] == ["行情涨跌数据不足，暂不给出仓位建议"]


def test_all_quote_fetches_failed_mood_unknown():
    """报价全线取数失败同样不能报"中性 / 波动平稳"。"""
    brief = _brief({
        "AAA": {"error": "quote source down"},
        "BBB": {"error": "quote source down"},
    })
    assert brief["market_mood"] == "unknown"
    assert brief["market_mood_cn"] == "数据不足"
    assert brief["priced_count"] == 0
    assert "整体情绪：中性" not in brief["summary"]
    assert brief["action_items"] == ["行情涨跌数据不足，暂不给出仓位建议"]
