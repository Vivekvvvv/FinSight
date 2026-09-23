# -*- coding: utf-8 -*-
"""R27: NewsAlertScheduler 标题相关性必须是「ticker 型 token」匹配，不是裸子串。

裸子串 `sub["ticker"].upper() in title.upper()` 让英文单词型真实代码
(T / F / ON / SO / ALL / NOW / ARE / CAN / IT / BE ...) 撞上几乎每篇
英文标题："T" ⊂ "MARKETS RALLY"，"ON" ⊂ "HORIZON"（词内子串）。
订阅这些 ticker 的用户会收到与其持仓无关的新闻提醒邮件。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.services.alert_scheduler import NewsAlertScheduler


class _SubService:
    def __init__(self, subs):
        self._subs = subs

    def get_subscriptions(self, allow_all=False):
        return list(self._subs)

    def is_valid_email(self, _email):
        return True

    def record_alert_attempt(self, *args, **kwargs):
        pass

    def update_last_news(self, *args, **kwargs):
        pass

    def update_last_risk(self, *args, **kwargs):
        pass

    def record_alert_event(self, *args, **kwargs):
        pass


class _Email:
    def __init__(self):
        self.sent = []

    def send_stock_alert(self, **kwargs):
        self.sent.append(kwargs)
        return True


def _sub(ticker: str) -> dict:
    return {
        "email": "u@example.com",
        "ticker": ticker,
        "alert_types": ["news"],
        "disabled": False,
    }


def _article(title: str, related=None) -> dict:
    return {
        "title": title,
        "source": "wire",
        "url": "https://example.com/a",
        "published_at": datetime.now(timezone.utc) - timedelta(hours=1),
        "related_tickers": list(related or []),
    }


def _run(ticker: str, articles: list[dict]) -> _Email:
    email = _Email()
    scheduler = NewsAlertScheduler(
        subscription_service=_SubService([_sub(ticker)]),
        email_service=email,
        news_fetcher=lambda _t: articles,
    )
    scheduler.run_once()
    return email


def test_single_letter_ticker_does_not_match_plain_title():
    # "T" (AT&T) 裸子串会命中几乎每个含字母 T 的英文标题。
    email = _run("T", [_article("Markets rally as Fed holds rates steady")])
    assert email.sent == []


def test_word_ticker_does_not_match_inside_longer_words():
    # "ON" (安森美) 裸子串命中 "HORIZ**ON**" / " **ON** " 等无关标题。
    email = _run("ON", [_article("Horizon Therapeutics jumps on trial results")])
    assert email.sent == []


def test_word_ticker_lowercase_word_does_not_match():
    # "ALL" (Allstate) 不应撞上小写单词 "all"/"Wall"。
    email = _run("ALL", [_article("Wall Street banks all report earnings")])
    assert email.sent == []


def test_real_ticker_uppercase_token_still_matches():
    # 真命中必须保留：标题里出现独立大写 ticker token。
    email = _run("AAPL", [_article("AAPL stock rises on earnings beat")])
    assert len(email.sent) == 1


def test_single_letter_ticker_related_tickers_path_still_works():
    # 单字母 ticker 不能靠标题匹配，但 related_tickers 精确命中仍应发送。
    email = _run("T", [_article("Telecom giants slide after open", related=["T"])])
    assert len(email.sent) == 1


# --- R28: 告警事件标题不能带 mojibake（UTF-8 源被按 GBK 解码过的乱码串） ---


class _SubServiceRecording(_SubService):
    def __init__(self, subs):
        super().__init__(subs)
        self.events = []

    def record_alert_event(self, *args, **kwargs):
        self.events.append(kwargs)


def _run_recording(ticker: str, articles: list[dict]) -> list[dict]:
    service = _SubServiceRecording([_sub(ticker)])
    scheduler = NewsAlertScheduler(
        subscription_service=service,
        email_service=_Email(),
        news_fetcher=lambda _t: articles,
    )
    scheduler.run_once()
    return service.events


def test_news_alert_event_title_is_not_mojibake():
    # 事件标题持久化进 alert 历史，用户可见；现串是 "相关新闻触发/条" 的乱码。
    events = _run_recording("AAPL", [_article("AAPL stock rises on earnings beat")])
    assert len(events) == 1
    title = events[0]["title"]
    assert "相关新闻触发" in title
    assert "条" in title


def test_risk_alert_event_title_is_not_mojibake():
    from backend.services.alert_providers import PriceSnapshot
    from backend.services.alert_scheduler import RiskAlertScheduler

    service = _SubServiceRecording([{**_sub("AAPL"), "alert_types": ["risk"]}])
    scheduler = RiskAlertScheduler(
        subscription_service=service,
        email_service=_Email(),
        price_fetcher=lambda _t: PriceSnapshot(ticker="AAPL", price=100.0, change_percent=9.0),
    )
    scheduler.run_once()
    assert len(service.events) == 1
    assert "风险等级" in service.events[0]["title"]
