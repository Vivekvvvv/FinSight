# -*- coding: utf-8 -*-
"""analyze_news_sentiment：LLM 返回数组里的非 dict 毒条目不得毁掉整批。

bug：enriched.update(sentiments[i]) 对非 dict 元素（str/int/None）抛
TypeError/ValueError，逃逸进函数级 except Exception → 全部新闻被换成
_neutral_sentiment，合法条目的真实分析结果一并丢失（R107-R123 同族：
一条毒记录毁一批）。顶层非 list 的合法 JSON（dict/标量）走同一异常路径。
"""
from __future__ import annotations

import asyncio
import json

import backend.llm_config as llm_config
from backend.services.news_sentiment import analyze_news_sentiment


class _FakeResponse:
    def __init__(self, content: str):
        self.content = content


class _FakeLLM:
    def __init__(self, content: str):
        self._content = content

    async def ainvoke(self, _prompt):
        return _FakeResponse(self._content)


def _patch_llm(monkeypatch, payload: str) -> None:
    monkeypatch.setattr(llm_config, "create_llm", lambda **_kwargs: _FakeLLM(payload))


_NEWS = [
    {"title": "新闻甲", "summary": "甲摘要"},
    {"title": "新闻乙", "summary": "乙摘要"},
    {"title": "新闻丙", "summary": "丙摘要"},
]


def test_poison_array_entry_degrades_per_item_not_batch(monkeypatch):
    """混入非 dict 条目：合法条目保真实分析，毒条目单独降 neutral。"""
    payload = json.dumps([
        {
            "sentiment": "positive", "sentiment_cn": "利好",
            "confidence": 0.9, "key_event": "业绩超预期", "impact_level": "high",
        },
        "junk-entry",
        {
            "sentiment": "negative", "sentiment_cn": "利空",
            "confidence": 0.8, "key_event": "监管处罚", "impact_level": "medium",
        },
    ], ensure_ascii=False)
    _patch_llm(monkeypatch, payload)

    result = asyncio.run(analyze_news_sentiment(_NEWS, "AAPL"))

    assert len(result) == 3
    # 修复前：update("junk-entry") 抛错 → 整批 neutral，本条断言即红
    assert result[0]["sentiment"] == "positive"
    assert result[0]["key_event"] == "业绩超预期"
    # 毒条目单独降级
    assert result[1]["sentiment"] == "neutral"
    assert result[1]["key_event"] == "暂无分析"
    assert result[2]["sentiment"] == "negative"


def test_top_level_non_list_degrades_to_neutral(monkeypatch):
    """顶层是合法 JSON 但非数组（dict）：全部按 neutral 兜底，不得 500/异常路径。"""
    _patch_llm(monkeypatch, json.dumps({"sentiment": "positive"}, ensure_ascii=False))

    result = asyncio.run(analyze_news_sentiment(_NEWS, "AAPL"))

    assert len(result) == 3
    assert all(item["sentiment"] == "neutral" for item in result)


def test_scalar_and_none_entries_degrade_per_item(monkeypatch):
    """数组混入 int / None：同样按条降级。"""
    payload = json.dumps([
        None,
        {"sentiment": "positive", "sentiment_cn": "利好",
         "confidence": 0.7, "key_event": "扩产", "impact_level": "low"},
        42,
    ], ensure_ascii=False)
    _patch_llm(monkeypatch, payload)

    result = asyncio.run(analyze_news_sentiment(_NEWS, "AAPL"))

    assert result[0]["sentiment"] == "neutral"
    assert result[1]["sentiment"] == "positive"
    assert result[2]["sentiment"] == "neutral"
