# -*- coding: utf-8 -*-
"""authoritative_feeds._extract_tickers：整句 .upper() 后按 \\b[A-Z]{1,5}\\b 提取。

修复前每个英文单词都被当成 ticker（"what is..."→["WHAT","IS"]、
"should I buy..."→["SHOULD","I"]），为假标的白拉 Yahoo RSS feed；
修复后委托 ticker_mapping.extract_tickers（KNOWN_TICKERS + 全大写显式
输入 + COMMON_WORDS 过滤），行为与全站 ticker 提取一致。
"""
from __future__ import annotations

import logging

from backend.tools import authoritative_feeds
from backend.tools.authoritative_feeds import _extract_tickers, get_authoritative_media_news


def test_ordinary_english_words_not_tickers():
    # 修复前：[:2] 取到 ["WHAT","IS"] → 为 "WHAT"/"IS" 拉 Yahoo feed
    assert _extract_tickers("what is the latest market news") == []


def test_pronoun_and_common_words_not_tickers():
    # 修复前 {1,5} 连大写单字母 "I" 都提取 → ["I","WANT"]
    assert _extract_tickers("I want market updates") == []


def test_uppercase_ticker_still_extracted():
    assert _extract_tickers("latest news for AAPL") == ["AAPL"]


def test_lowercase_known_ticker_kept():
    # KNOWN_TICKERS 大小写不敏感——修复前靠整句 upper 才有此召回
    assert "AAPL" in _extract_tickers("aapl earnings preview")


def test_chinese_company_maps_to_feed_ticker():
    # 委托 canonical extractor 后中文名也能定向（修复前提取不到任何 ticker）
    assert _extract_tickers("苹果最新研报") == ["AAPL"]


def test_capped_at_two():
    assert _extract_tickers("AAPL MSFT NVDA TSLA") == ["AAPL", "MSFT"]


def test_feed_fetch_failure_is_not_a_measured_empty_result(monkeypatch, caplog):
    """四个 feed 全部取数失败时，search_authoritative_feeds 返回 []，
    与"本次确实没有权威报道"在结构上同形：wrapper 此前照旧吐
    articles=[] + error=None，下游把它当成关于 query 的事实结论
    （项目规则 2、finsight-silent-success-forbidden）。
    """
    def _boom(*_args, **_kwargs):
        raise RuntimeError("PRIVATE_FEED_CONNECTION_DETAIL")

    monkeypatch.setattr(authoritative_feeds, "_http_get", _boom)

    with caplog.at_level(logging.WARNING):
        payload = get_authoritative_media_news("AAPL latest news")

    assert payload["articles"] == []
    assert payload["error"] == "authoritative_feed_unavailable"
    assert "authoritative feed request failed" in caplog.text
    assert "PRIVATE_FEED_CONNECTION_DETAIL" not in caplog.text


def test_successful_empty_feed_stays_a_real_empty_result(monkeypatch, caplog):
    """真·空结果（feed 取得到、只是没有匹配文章）不能被降级原因污染。"""
    monkeypatch.setattr(authoritative_feeds, "_http_get", lambda *_a, **_k: _Resp("<rss></rss>"))

    with caplog.at_level(logging.WARNING):
        payload = get_authoritative_media_news("AAPL latest news")

    assert payload["articles"] == []
    assert payload["error"] is None
    assert "authoritative feed request failed" not in caplog.text


def test_degradation_flag_does_not_leak_into_the_next_call(monkeypatch):
    """降级标记是模块级、每次调用开头重置：一次故障不能让后续
    正常请求也被标成降级。"""
    def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(authoritative_feeds, "_http_get", _boom)
    assert get_authoritative_media_news("AAPL latest news")["error"] == "authoritative_feed_unavailable"

    monkeypatch.setattr(authoritative_feeds, "_http_get", lambda *_a, **_k: _Resp("<rss></rss>"))
    assert get_authoritative_media_news("AAPL latest news")["error"] is None


class _Resp:
    status_code = 200

    def __init__(self, text: str):
        self.text = text
