# -*- coding: utf-8 -*-
"""R74：score_news_source_reliability 的 source 提示词用裸 `hint in lowered`
子串匹配——"sec" 命中 "security"/"second"，非SEC来源继承 0.98 权威分
（domain 侧已做整域/".hint"结尾边界，source 侧漏了）。news_agent 按
reliability_score/tier 给证据加权，幻影命中直接污染权重。
≤3 字符 ASCII hint 改走非字母数字边界，与 _keyword_match/_match_any 同策略。"""
from __future__ import annotations

from backend.tools.news import score_news_source_reliability


def test_securityweek_not_sec():
    """"SecurityWeek" 里的 "sec" 子串不该继承 SEC 0.98 权威分。"""
    out = score_news_source_reliability(source="SecurityWeek", url="")
    assert out["reliability_score"] != 0.98
    assert out["reason"] != "source:sec"


def test_reuters_security_desk_gets_reuters_score():
    """"Reuters Security" 应先越过 "security" 里的幻影 "sec"，落到 reuters。"""
    out = score_news_source_reliability(source="Reuters Security", url="")
    assert out["reliability_score"] == 0.95
    assert out["reason"] == "source:reuters"


def test_second_nexus_not_sec():
    """"Second Nexus" 里的 "sec" 子串不该命中。"""
    out = score_news_source_reliability(source="Second Nexus", url="")
    assert out["reliability_score"] != 0.98


def test_legit_sec_source_still_scores():
    """独立成词的 "SEC" 仍命中 0.98——回归保护。"""
    out = score_news_source_reliability(source="SEC Filings", url="")
    assert out["reliability_score"] == 0.98
    assert out["reason"] == "source:sec"


def test_legit_wsj_source_still_scores():
    """独立成词的 "WSJ" 仍命中 0.92——回归保护。"""
    out = score_news_source_reliability(source="WSJ", url="")
    assert out["reliability_score"] == 0.92


def test_multiword_hint_still_substring():
    """多词 hint 保留子串匹配——"The Wall Street Journal" 命中 0.92。"""
    out = score_news_source_reliability(source="The Wall Street Journal", url="")
    assert out["reliability_score"] == 0.92


def test_domain_boundary_unchanged():
    """domain 侧整域/子域边界不变——sec.gov 0.98、仿冒域不得分。"""
    legit = score_news_source_reliability(source="", url="https://sec.gov/x")
    assert legit["reliability_score"] == 0.98
    fake = score_news_source_reliability(source="", url="https://sec.gov.evil.example/x")
    assert fake["reliability_score"] == 0.55
