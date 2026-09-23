# -*- coding: utf-8 -*-
"""R72：authoritative_feeds._matches_query 用裸 `token in haystack` 子串匹配——
_query_tokens 保留 ≥2 字符的 ASCII token，"ai" 命中 "said"/"again"、
"us" 命中 "versus"/"plus"：任何含短 token 的查询都让相关性过滤退化成
全放行（any() 里短 token 恒真），无关条目挤占 max_results 名额。
与同包 news_rss_tools._keyword_match（≤3 字符 isalpha 走 \b 边界）及
parse_operation._match_any / planner_stub._contains_any 同一策略对齐。"""
from __future__ import annotations

from backend.tools.authoritative_feeds import _matches_query, _query_tokens


def test_ai_token_does_not_match_inside_said():
    """"said" 里的 "ai" 子串不该让无关条目通过 ai 查询。"""
    tokens = _query_tokens("ai regulation")
    assert "ai" in tokens  # 确认短 token 确实被提取、走的是该路径
    item = {"title": "Fed said to hold rates steady", "snippet": "", "url": ""}
    assert _matches_query(item, tokens) is False


def test_us_token_does_not_match_inside_versus():
    """"versus"/"plus" 里的 "us" 子串不该命中 us 查询。"""
    tokens = _query_tokens("us tariffs")
    assert "us" in tokens
    item = {"title": "Stoxx versus Nikkei: plus points compared", "snippet": "", "url": ""}
    assert _matches_query(item, tokens) is False


def test_ev_token_does_not_match_inside_every():
    """"every" 里的 "ev" 子串不该命中 ev 查询。"""
    item = {"title": "Central banks weigh every option", "snippet": "", "url": ""}
    assert _matches_query(item, ["ev"]) is False


def test_legit_ai_keyword_still_matches():
    """独立成词的 "AI" 仍命中——回归保护。"""
    tokens = _query_tokens("ai chips")
    item = {"title": "AI chip demand lifts suppliers", "snippet": "", "url": ""}
    assert _matches_query(item, tokens) is True


def test_legit_us_keyword_still_matches():
    """独立成词的 "US" 仍命中——回归保护。"""
    tokens = _query_tokens("us economy")
    item = {"title": "US economy cools as spending slows", "snippet": "", "url": ""}
    assert _matches_query(item, tokens) is True


def test_long_token_substring_recall_kept():
    """更长 token 保留子串匹配召回——"semiconductor" 命中 "semiconductors"。"""
    item = {"title": "Semiconductors rally on demand", "snippet": "", "url": ""}
    assert _matches_query(item, ["semiconductor"]) is True


def test_cjk_token_still_substring():
    """CJK token 无词边界概念，保留子串匹配——"半导体" 命中 "半导体行业"。"""
    item = {"title": "半导体行业景气回升", "snippet": "", "url": ""}
    assert _matches_query(item, ["半导体"]) is True
