"""Pure URL/text helpers for the news agent (extracted from agents/news_agent.py)."""

from __future__ import annotations

from typing import Any, Dict, List
from urllib.parse import parse_qs, unquote, urlparse


def _domain_from_url(url: str) -> str:
    try:
        host = urlparse(str(url or "").strip()).hostname or ""
    except Exception:
        host = ""
    # removeprefix 而非 lstrip：lstrip("www.") 按字符集合 {w,.} 剥，
    # "www.wsj.com" → "sj.com"，权威 hint 子串匹配 "wsj.com" in "sj.com"
    # 失败 → WSJ 新闻被 _filter_authoritative_news 全丢（R20 同类，R48）。
    return host.lower().removeprefix("www.")


def _recover_original_article_url(url: str) -> str:
    text = str(url or "").strip()
    if not text.startswith(("http://", "https://")):
        return ""
    try:
        parsed = urlparse(text)
    except Exception:
        return ""

    domain = (parsed.hostname or "").lower().removeprefix("www.")
    path = (parsed.path or "").lower()
    query = parse_qs(parsed.query)

    if domain == "finnhub.io" and path.startswith("/api/news"):
        for key in ("url", "article_url", "link", "u"):
            value = query.get(key, [None])[0]
            if not value:
                continue
            decoded = unquote(str(value)).strip()
            if decoded.startswith(("http://", "https://")):
                return decoded
        return ""

    if domain == "news.google.com":
        for key in ("url", "u"):
            value = query.get(key, [None])[0]
            if not value:
                continue
            decoded = unquote(str(value)).strip()
            if decoded.startswith(("http://", "https://")):
                return decoded

    return text


def _is_authoritative_domain(domain: str, hints: tuple[str, ...]) -> bool:
    # hints 必填：唯一真源是 NewsAgent._AUTHORITATIVE_DOMAIN_HINTS。此处曾有一份
    # 同内容的模块级默认值，但唯一调用方总是显式传参，那份默认值走不到，
    # 改动时也不会有测试失败 —— 两份字面量只会静默漂移。
    host = str(domain or "").strip().lower()
    if not host:
        return False
    # 裸子串匹配会让 reuters.com.evil.example / notreuters.com 这类仿冒主机、
    # 以及 drift.com→"ft.com" 这类字符巧合继承权威身份。
    # 域名 hint 只认整域或 ".hint" 结尾的合法子域；
    # 带尾点的 "investor." 是前缀型 hint（investor.<issuer>.com），按 startswith 匹配。
    for hint in hints:
        if hint.endswith("."):
            if host.startswith(hint):
                return True
        elif host == hint or host.endswith("." + hint):
            return True
    return False


def _parse_news_text(news_text: str, ticker: str) -> List[Dict[str, Any]]:
    """解析 get_company_news 返回的格式化文本为结构化数据"""
    import re
    results = []

    # 格式示例: "1. 2025-01-13 - [Title](url) - Source [Tags]"
    lines = news_text.split('\n')
    for line in lines:
        if not line.strip() or line.startswith('Latest'):
            continue

        # 提取标题和URL
        url_match = re.search(r'\[([^\]]+)\]\(([^)]+)\)', line)
        if url_match:
            title = url_match.group(1)
            url = url_match.group(2)
        else:
            # 没有URL格式，直接提取文本
            title = re.sub(r'^\d+\.\s*[\d-]*\s*-?\s*', '', line).strip()
            url = ""

        # 提取日期
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', line)
        date_str = date_match.group(1) if date_match else ""

        # 提取来源
        source_match = re.search(r'-\s+([A-Za-z0-9\s]+)\s*\[', line)
        source = source_match.group(1).strip() if source_match else "Unknown"

        if title and len(title) > 10:
            results.append({
                "headline": title,
                "title": title,
                "url": url,
                "source": source,
                "datetime": date_str,
                "published_at": date_str,
                "ticker": ticker,
                "confidence": 0.7,
            })

    return results


def _parse_search_results(search_text: str, ticker: str) -> List[Dict[str, Any]]:
    """解析搜索结果为新闻格式"""
    import re
    results = []

    lines = search_text.split('\n')
    for line in lines:
        if not line.strip():
            continue

        # 提取URL
        url_match = re.search(r'https?://[^\s\)]+', line)
        url = url_match.group(0) if url_match else ""

        # 提取标题（去除URL和标点）
        title = re.sub(r'https?://[^\s]+', '', line)
        title = re.sub(r'^\d+\.\s*', '', title).strip()
        title = title[:150] if len(title) > 150 else title

        if title and len(title) > 15:
            results.append({
                "headline": title,
                "title": title,
                "url": url,
                "source": "search",
                "published_at": None,
                "datetime": None,
                "ticker": ticker,
                "confidence": 0.4,
            })

    return results[:5]  # 限制数量
