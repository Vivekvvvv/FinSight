# -*- coding: utf-8 -*-
"""R48 回归：www. 前缀剥离必须用 removeprefix，不能用 lstrip。

lstrip("www.") 剥的是字符集合 {w,.}，"www.wsj.com" 被剥成 "sj.com"
（连 wsj 首字母一起吃），导致 wsj.com 权威匹配失败、WSJ 被全量丢弃。
R20 修过 tools/news.py，authoritative_feeds.py 与 agents/news_agent.py 漏传播。
"""
from __future__ import annotations

import logging


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
    assert _normalize_domain("https://reuters.com@evil.xyz/article") == "evil.xyz"


def test_news_agent_domain_strip_keeps_wsj():
    from backend.agents.news_agent import NewsAgent

    agent = NewsAgent.__new__(NewsAgent)  # 只测纯函数，绕过 __init__ 的依赖注入
    # www.wsj.com → wsj.com，而非 sj.com
    assert agent._domain_from_url("https://www.wsj.com/markets/x") == "wsj.com"
    # 权威过滤必须保留 WSJ
    assert agent._is_authoritative_domain(agent._domain_from_url("https://www.wsj.com/x")) is True
    # 非 w 开头域名回归保护
    assert agent._domain_from_url("https://finance.yahoo.com/news/x") == "finance.yahoo.com"
    assert agent._domain_from_url("https://wsj.com@evil.xyz/news/x") == "evil.xyz"


def test_deep_search_domain_strip_keeps_wsj():
    from backend.agents.deep_search_agent import DeepSearchAgent

    agent = DeepSearchAgent.__new__(DeepSearchAgent)
    assert agent._normalized_domain_from_url("https://www.wsj.com/markets/x") == "wsj.com"
    assert agent._is_trusted_finance_domain("www.wsj.com") is True
    disguised = agent._normalized_domain_from_url("https://wsj.com@evil.xyz/markets/x")
    assert disguised == "evil.xyz"
    assert agent._is_trusted_finance_domain(disguised) is False
    assert agent._infer_source("https://user:secret@example.com/x") == "example.com"
    assert agent._is_blocked_result({"url": "https://[broken"}) is True
    assert agent._infer_source("https://[broken") == "web"


def test_other_source_domain_normalizers_remove_only_exact_www_prefix():
    from backend.tools.earnings_transcripts import _normalize_domain as transcript_domain
    from backend.tools.local_disclosure import _normalize_domain as disclosure_domain
    from backend.tools.macro_official import _normalize_domain as macro_domain
    from backend.tools.wayback import _normalize_domain as wayback_domain

    for normalize in (transcript_domain, disclosure_domain, macro_domain, wayback_domain):
        assert normalize("https://www.wsj.com/articles/x") == "wsj.com"
        assert normalize("https://ww2.example.com/x") == "ww2.example.com"
        assert normalize("https://trusted.example@evil.xyz/x") == "evil.xyz"

    from backend.tools.news import _domain_from_url as news_domain

    assert news_domain("https://www.wsj.com/articles/x") == "wsj.com"
    assert news_domain("https://wsj.com@evil.xyz/articles/x") == "evil.xyz"


def test_report_builder_domain_checks_ignore_url_userinfo():
    from backend.graph.report_builder import _canonicalize_url_for_citation_match, _is_suspicious_citation_item

    item = {
        "url": "https://sec.gov@evil.xyz/article",
        "title": "Market update",
        "snippet": "Public filing analysis",
    }
    assert _is_suspicious_citation_item(item) is True
    assert _canonicalize_url_for_citation_match(item["url"]) == ""
    assert _is_suspicious_citation_item({"url": "https://[broken"}) is True


def test_feed_failure_logs_omit_url_credentials(monkeypatch, caplog):
    from backend.tools import authoritative_feeds, macro_official, news

    secret = "PRIVATE_RSS_PASSWORD"
    target = f"https://user:{secret}@feeds.example.com/private.xml"

    def _fail(*_args, **_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(authoritative_feeds, "_http_get", _fail)
    monkeypatch.setattr(macro_official, "_http_get", _fail)
    monkeypatch.setattr(news, "_rss_get", _fail)
    caplog.set_level(logging.DEBUG)

    assert authoritative_feeds._fetch_feed(target) == ""
    assert macro_official._fetch_feed(target) == ""
    assert news._fetch_rss_headlines([target]) == ([], False)
    assert secret not in caplog.text
    assert "feeds.example.com" in caplog.text
