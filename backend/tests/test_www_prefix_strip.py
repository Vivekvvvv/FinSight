# -*- coding: utf-8 -*-
"""R48 回归：www. 前缀剥离必须用 removeprefix，不能用 lstrip。

lstrip("www.") 剥的是字符集合 {w,.}，"www.wsj.com" 被剥成 "sj.com"
（连 wsj 首字母一起吃），导致 wsj.com 权威匹配失败、WSJ 被全量丢弃。
R20 修过 tools/news.py，authoritative_feeds.py 与 agents/news_agent.py 漏传播。
"""
from __future__ import annotations


def test_authoritative_feeds_recognizes_wsj():
    from backend.tools.authoritative_feeds import _normalize_domain, _is_authoritative_domain

    # www.wsj.com 必须归一到 wsj.com（而非 lstrip 的 sj.com）
    assert _normalize_domain("https://www.wsj.com/articles/x") == "wsj.com"
    assert _is_authoritative_domain("www.wsj.com") is True
    assert _is_authoritative_domain("wsj.com") is True
    # 子域名仍走 endswith 分支
    assert _is_authoritative_domain("feeds.a.dj.com") is False  # dj.com 不在权威集
    # 非 w 开头域名不受影响（回归保护）
    assert _is_authoritative_domain("reuters.com") is True


def test_news_agent_domain_strip_keeps_wsj():
    from backend.agents.news_agent import NewsAgent

    agent = NewsAgent.__new__(NewsAgent)  # 只测纯函数，绕过 __init__ 的依赖注入
    # www.wsj.com → wsj.com，而非 sj.com
    assert agent._domain_from_url("https://www.wsj.com/markets/x") == "wsj.com"
    # 权威过滤必须保留 WSJ
    assert agent._is_authoritative_domain(agent._domain_from_url("https://www.wsj.com/x")) is True
    # 非 w 开头域名回归保护
    assert agent._domain_from_url("https://finance.yahoo.com/news/x") == "finance.yahoo.com"
