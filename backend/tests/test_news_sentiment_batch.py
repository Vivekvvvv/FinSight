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

import pytest

import backend.llm_config as llm_config


@pytest.mark.parametrize("identity", [{"ticker": "MSFT"}, {"symbol": "MSFT"}, {"ticker": {}}])
def test_model_sentiment_for_another_instrument_is_marked_unavailable(monkeypatch, identity):
    _patch_llm(monkeypatch, json.dumps([{"sentiment": "positive", **identity}]))
    result = asyncio.run(analyze_news_sentiment([{"title": "AAPL news"}], ticker="AAPL"))[0]
    assert result["analysis_status"] == "unavailable"
    assert result["confidence"] == 0


@pytest.mark.parametrize("identity", [{"ticker": "MSFT"}, {"symbol": "MSFT"}, {"ticker": {}}])
def test_sentiment_analysis_excludes_explicit_other_instrument_news(monkeypatch, identity):
    _patch_llm(monkeypatch, '[{"sentiment":"positive"}]')
    news = [{"title": "Wrong headline", **identity}, {"title": "Actual", "symbol": " aapl "}]
    result = asyncio.run(analyze_news_sentiment(news, ticker="AAPL"))
    assert [row["title"] for row in result] == ["Actual"]
    assert result[0]["sentiment"] == "positive"


def test_sentiment_prompt_uses_text_evidence_and_skips_rows_without_text(monkeypatch):
    prompts = []
    class LLM:
        async def ainvoke(self, prompt):
            prompts.append(prompt)
            return _FakeResponse('[{"sentiment":"positive"},{"sentiment":"negative"}]')
    monkeypatch.setattr(llm_config, "create_llm", lambda **kwargs: LLM())
    news = [{"title": {"bad": True}, "summary": 42},
            {"title": {"bad": True}, "summary": "actual summary"},
            {"title": "valid title", "summary": {"bad": True}, "content": "actual content"}]
    result = asyncio.run(analyze_news_sentiment(news))
    assert len(result) == 2
    assert [row["sentiment"] for row in result] == ["positive", "negative"]
    assert "actual summary" in prompts[0] and "actual content" in prompts[0]
    assert '"bad"' not in prompts[0]
    assert result[0]["title"] == {"bad": True}


@pytest.mark.parametrize("failure", [{"success": False}, {"error": "bad"}, {"status": " Failed "}])
def test_failed_source_news_cannot_use_model_slots_or_relabel_valid_analysis(monkeypatch, failure):
    prompts = []
    class LLM:
        async def ainvoke(self, prompt):
            prompts.append(prompt)
            return _FakeResponse('[{"sentiment":"negative","confidence":0.8}]')
    monkeypatch.setattr(llm_config, "create_llm", lambda **kwargs: LLM())
    news = [{"title": "failed source", **failure}, {"title": "valid source"}]
    result = asyncio.run(analyze_news_sentiment(news))
    assert [row["title"] for row in result] == ["valid source"]
    assert result[0]["sentiment"] == "negative"
    assert "failed source" not in prompts[0]
    assert asyncio.run(analyze_news_sentiment(news[:1])) == []
    assert len(prompts) == 1
from backend.services.news_sentiment import (
    SentimentAnalysisUnavailable,
    analyze_news_sentiment,
)


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


@pytest.mark.parametrize("label, expected, chinese", [
    (" POSITIVE ", "positive", "利好"),
    ("Negative", "negative", "利空"),
    (" NEUTRAL ", "neutral", "中性"),
])
def test_model_sentiment_labels_are_canonical_and_consistent(monkeypatch, label, expected, chinese):
    _patch_llm(monkeypatch, json.dumps([{"sentiment": label, "sentiment_cn": "矛盾标签"}]))

    result = asyncio.run(analyze_news_sentiment(_NEWS[:1]))[0]

    assert result["sentiment"] == expected
    assert result["sentiment_cn"] == chinese
    assert result["analysis_status"] == "success"


@pytest.mark.parametrize("failure", [
    {"error": "unavailable"}, {"success": False}, {"status": "FAILED"},
    {"analysis_status": " unavailable "}, {"analysis_status": "error"},
])
def test_failed_model_row_is_excluded_without_losing_other_news(monkeypatch, failure):
    from backend.services.news_sentiment import aggregate_sentiment

    _patch_llm(monkeypatch, json.dumps([
        {**failure, "sentiment": "positive", "confidence": 0.9},
        {"sentiment": "negative", "confidence": 0.8},
    ]))

    result = asyncio.run(analyze_news_sentiment(_NEWS[:2]))

    assert result[0]["analysis_status"] == "unavailable"
    assert result[1]["analysis_status"] == "success"
    assert aggregate_sentiment(result)["positive"] == 0
    assert aggregate_sentiment(result)["negative"] == 1


@pytest.mark.parametrize("event, impact, expected_event, expected_impact", [
    ({"text": "event"}, ["high"], "", "low"),
    (None, "invalid", "", "low"),
    ("  业绩增长  ", " HIGH ", "业绩增长", "high"),
    ("事件" * 20, "Medium", ("事件" * 20)[:30], "medium"),
])
def test_model_display_fields_have_safe_shapes(monkeypatch, event, impact, expected_event, expected_impact):
    _patch_llm(monkeypatch, json.dumps([{
        "sentiment": "positive", "key_event": event, "impact_level": impact,
    }]))

    result = asyncio.run(analyze_news_sentiment(_NEWS[:1]))[0]

    assert result["key_event"] == expected_event
    assert result["impact_level"] == expected_impact
    assert result["analysis_status"] == "success"


@pytest.mark.parametrize("failure", [
    {"error": "failed"}, {"success": False}, {"status": " ERROR "},
    {"analysis_status": "Failed"}, {"analysis_status": " UNAVAILABLE "},
])
def test_aggregate_excludes_failed_retained_analysis(failure):
    from backend.services.news_sentiment import aggregate_sentiment

    result = aggregate_sentiment([
        {**failure, "sentiment": "positive", "impact_level": "high"},
        {"sentiment": "negative", "impact_level": "low", "analysis_status": "success"},
    ])

    assert result["positive"] == 0
    assert result["negative"] == 1
    assert result["score"] == -33.3


def test_unusable_reanalysis_does_not_keep_old_sentiment(monkeypatch):
    from backend.services.news_sentiment import aggregate_sentiment

    _patch_llm(monkeypatch, "[{}]")
    result = asyncio.run(analyze_news_sentiment([{
        "title": "Original", "sentiment": "positive", "confidence": 0.9,
        "impact_level": "high", "key_event": "Old analysis", "analysis_status": "success",
    }]))

    assert result[0]["analysis_status"] == "unavailable"
    assert result[0]["key_event"] == "暂无分析"
    assert aggregate_sentiment(result)["positive"] == 0


def test_successful_reanalysis_replaces_old_unavailable_status(monkeypatch):
    from backend.services.news_sentiment import aggregate_sentiment

    _patch_llm(monkeypatch, '[{"sentiment":"negative","confidence":0.8}]')
    result = asyncio.run(analyze_news_sentiment([{"title": "Original", "analysis_status": "unavailable"}]))

    assert result[0]["analysis_status"] == "success"
    assert aggregate_sentiment(result)["negative"] == 1


def test_original_news_fields_cannot_be_overwritten_by_model(monkeypatch):
    news = {"title": "Original", "url": "https://example.com/news", "ticker": "AAPL"}
    _patch_llm(monkeypatch, json.dumps([{**news, "title": "Forged", "url": "https://evil.example", "ticker": "MSFT", "sentiment": "positive"}]))
    result = asyncio.run(analyze_news_sentiment([news]))[0]
    for key in news:
        assert result[key] == news[key]
    assert result["sentiment"] == "positive"


def test_model_cannot_analyse_news_that_was_not_in_the_prompt(monkeypatch):
    from backend.services.news_sentiment import aggregate_sentiment

    news = [{"title": f"News {index}"} for index in range(17)]
    _patch_llm(monkeypatch, json.dumps([{"sentiment": "positive", "confidence": 0.9}] * 17))

    result = asyncio.run(analyze_news_sentiment(news))

    assert all(item["analysis_status"] == "unavailable" for item in result[15:])
    assert aggregate_sentiment(result)["positive"] == 15


def test_unanalysed_tail_has_no_fabricated_confidence_or_neutral_count(monkeypatch):
    from backend.services.news_sentiment import aggregate_sentiment
    news = [{"title": f"News {i}"} for i in range(17)]
    _patch_llm(monkeypatch, json.dumps([{"sentiment": "positive", "confidence": 0.9}] * 15))
    result = asyncio.run(analyze_news_sentiment(news))
    assert result[-1].get("analysis_status") == "unavailable"
    assert result[-1]["confidence"] == 0.0
    aggregate = aggregate_sentiment(result)
    assert aggregate["positive"] == 15
    assert aggregate["neutral"] == 0


def test_invalid_model_confidence_is_unknown_without_losing_valid_sentiment(monkeypatch):
    for raw, expected in ((True, None), (-0.1, None), (1.1, None), ("0.8", 0.8)):
        _patch_llm(monkeypatch, json.dumps([{"sentiment": "positive", "confidence": raw}]))
        result = asyncio.run(analyze_news_sentiment(_NEWS[:1]))[0]
        assert result["confidence"] == expected
        assert result["sentiment"] == "positive"


@pytest.mark.parametrize("declared, normalized", [(" HIGH ", "high"), ("Medium", "medium"), (" LOW ", "low")])
def test_aggregate_impact_weights_ignore_case_and_whitespace(declared, normalized):
    from backend.services.news_sentiment import aggregate_sentiment

    result = aggregate_sentiment([
        {"sentiment": "positive", "impact_level": declared},
        {"sentiment": "negative", "impact_level": normalized},
    ])

    assert result["score"] == 0.0
    assert result["overall_sentiment"] == "neutral"


def test_aggregate_only_analysed_labels_and_normalize_case():
    from backend.services.news_sentiment import aggregate_sentiment
    result = aggregate_sentiment([
        {"sentiment": " POSITIVE ", "impact_level": "high"},
        {"sentiment": "negative", "impact_level": "high"},
        {"title": "No analysis"},
        {"sentiment": "invalid"},
    ])
    assert result["positive"] == result["negative"] == 1
    assert result["neutral"] == 0
    assert result["score"] == 0


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


class _BrokenLLM:
    async def ainvoke(self, _prompt):
        raise RuntimeError("llm down")


def test_llm_failure_raises_instead_of_fake_neutral(monkeypatch):
    """LLM 调用失败时不许把每条新闻标成中性/0.5 当成真实分析。"""
    monkeypatch.setattr(llm_config, "create_llm", lambda **_kwargs: _BrokenLLM())

    with pytest.raises(SentimentAnalysisUnavailable):
        asyncio.run(analyze_news_sentiment(_NEWS, "AAPL"))


def test_non_json_response_raises_instead_of_fake_neutral(monkeypatch):
    """LLM 返回非 JSON 同样表示整批分析失败，不能降级成中性结论。"""
    _patch_llm(monkeypatch, "not-json")

    with pytest.raises(SentimentAnalysisUnavailable):
        asyncio.run(analyze_news_sentiment(_NEWS, "AAPL"))
