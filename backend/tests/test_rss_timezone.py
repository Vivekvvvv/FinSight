# -*- coding: utf-8 -*-
"""R54 回归：RSS pubDate 归一到 UTC，而非服务器本地时区。

_parse_rss_items 的 now 是 naive-UTC，但此前把带时区的 pubDate 用
astimezone(tz=None) 转成服务器本地时区再 strip，两者相减在非 UTC 部署
（中国 UTC+8）下偏移一个时区，48h 窗口漏进更老文章，date_str 也与
Finnhub 路径（UTC）不一致。归一到 UTC 后过滤与展示都以 UTC 为基准。
"""
from __future__ import annotations

from datetime import datetime

from backend.tools.news import _parse_rss_items


def _xml(*items: str) -> str:
    body = "".join(items)
    return f"<rss><channel>{body}</channel></rss>"


def _item(title: str, pub_date: str) -> str:
    return (
        f"<item><title>{title}</title>"
        f"<link>https://www.reuters.com/markets/x</link>"
        f"<pubDate>{pub_date}</pubDate></item>"
    )


def test_rss_pubdate_date_str_uses_utc_not_local():
    now = datetime(2026, 1, 10, 0, 0, 0)  # naive UTC
    # 09 Jan 05:00 +0800 == 08 Jan 21:00 UTC → 展示日期必须是 UTC 日 2026-01-08，
    # 而非本地(UTC+8)日 2026-01-09。
    xml = _xml(_item("Apple beats Q4 earnings estimates strongly", "Fri, 09 Jan 2026 05:00:00 +0800"))
    lines, ok = _parse_rss_items(xml, limit=5, max_age_days=2, now=now)
    assert ok and lines
    assert "2026-01-08" in lines[0], lines[0]


def test_rss_age_filter_keeps_fresh_drops_stale():
    now = datetime(2026, 1, 10, 0, 0, 0)  # naive UTC
    xml = _xml(
        # 08 Jan 21:00 UTC，距 now 约 1 天 3 小时 → 保留
        _item("Nvidia raises full year revenue outlook", "Fri, 09 Jan 2026 05:00:00 +0800"),
        # 04 Jan 21:00 UTC，距 now 约 5 天 → 过滤
        _item("Tesla delivery numbers miss street expectations", "Sun, 05 Jan 2026 05:00:00 +0800"),
    )
    lines, ok = _parse_rss_items(xml, limit=5, max_age_days=2, now=now)
    assert ok
    joined = "\n".join(lines)
    assert "Nvidia" in joined
    assert "Tesla" not in joined
