import logging
import os
import re
import time
from datetime import UTC, datetime, timedelta, date
from typing import Optional, List, Dict, Any

import yfinance as yf

from .env import ALPHA_VANTAGE_API_KEY, finnhub_client
from .http import _http_get
from .search import search
from backend.utils.quote import safe_float, safe_int

logger = logging.getLogger(__name__)

from backend.tools.news_rss_tools import (
    _RSS_SESSION,
    _RSS_TIMEOUT,
    _RSS_MAX_RETRIES,
    _MAX_RSS_FEEDS,
    NEWS_TAG_RULES,
    _get_rss_session,
    _rss_get,
    _is_reasonable_headline,
    _get_env_int,
    _contains_cjk,
    _headline_is_useful,
    _keyword_match,
    _headline_tags,
    _format_headline_line,
    _domain_from_url,
    _extract_datetime_from_text,
    _extract_datetime_from_url,
    _build_news_item,
    format_news_items,
    _parse_rss_items,
    _fetch_rss_headlines,
)

from backend.tools.news_search_tools import (
    _build_search_news_items,
    _fetch_finnhub_market_news,
    _format_search_news_items,
    _to_date_candidate,
    _within_window,
)


# ── RSS-dedicated lightweight session ────────────────────────────


MARKET_INDICES = {
    "^GSPC": "S&P 500 index",
    "^IXIC": "Nasdaq Composite index", 
    "^DJI": "Dow Jones Industrial Average",
    "^RUT": "Russell 2000 index",
    "^VIX": "VIX volatility index",
    "^NYA": "NYSE Composite index",
    "^FTSE": "FTSE 100 index",
    "^N225": "Nikkei 225 index",
    "^HSI": "Hang Seng index"
}


# NOTE: NEWS_TAG_RULES is defined once at module top level (line ~55).
# Removed duplicate definition that was previously here.


MARKET_INDICES = {
    "^GSPC": "S&P 500 index",
    "^IXIC": "Nasdaq Composite index", 
    "^DJI": "Dow Jones Industrial Average",
    "^RUT": "Russell 2000 index",
    "^VIX": "VIX volatility index",
    "^NYA": "NYSE Composite index",
    "^FTSE": "FTSE 100 index",
    "^N225": "Nikkei 225 index",
    "^HSI": "Hang Seng index"
}


def _is_market_index(ticker: str) -> bool:
    """判断ticker是否为市场指数"""
    # 方法1: 检查是否在已知指数列表中
    if ticker in MARKET_INDICES:
        return True
    
    # 方法2: 检查常见指数命名模式
    index_patterns = [
        r'^\^',      # 以 ^ 开头（Yahoo Finance指数标记）
        r'SPX$',     # S&P 500 的另一种写法
        r'NDX$',     # Nasdaq 100
        r'DJI$',     # Dow Jones
    ]
    
    for pattern in index_patterns:
        if re.match(pattern, ticker):
            return True
    
    return False


def _get_index_news(ticker: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    专门为市场指数获取新闻的方法（结构化输出）。
    策略：通过搜索获取宏观市场新闻和指数分析。
    """
    friendly_name = MARKET_INDICES.get(ticker, ticker.replace('^', ''))
    
    logger.info("  → Detected market index")
    logger.info(f"  → Using specialized search strategy for index news...")
    
    # 策略1: 搜索指数最近表现和分析
    current_date = datetime.now().strftime('%B %Y')
    search_queries = [
        f"{friendly_name} recent performance analysis {current_date}",
        f"{friendly_name} market news today",
        f"What's driving {friendly_name} this week"
    ]
    
    all_results = []
    for query in search_queries[:2]:  # 只用前2个查询，避免过多请求
        try:
            results = search(query)
            if results and "No search results" not in results:
                all_results.append(results)
            time.sleep(1)
        except Exception as e:
            logger.info("  → Search failed: %s", type(e).__name__)
            continue
    
    if not all_results:
        return []
    
    # 解析并格式化搜索结果
    combined_results = "\n\n".join(all_results)
    
    # 尝试从搜索结果中提取新闻标题和日期
    news_items: List[Dict[str, Any]] = []
    lines = combined_results.split('\n')
    
    for i, line in enumerate(lines):
        # 寻找标题模式（通常以数字开头）
        if re.match(r'^\d+\.', line.strip()):
            raw_title = line.strip()
            title = re.sub(r'^\d+\.\s*', '', raw_title).strip()
            window = ' '.join(lines[i:i+3])
            # 尝试找到日期信息
            date_match = re.search(r'(\d{1,2}\s+\w+\s+ago|\d{4}-\d{2}-\d{2}|\w+\s+\d{1,2},?\s+\d{4})', 
                                  window, re.IGNORECASE)
            if not _is_reasonable_headline(title, window):
                continue
            if not _headline_is_useful(title, window):
                continue
            date_str = date_match.group(1) if date_match else 'Recent'
            item = _build_news_item(
                title=title,
                source="search",
                url="",
                published_at=date_str,
                snippet=window,
                ticker=ticker,
                confidence=0.4,
            )
            if item:
                news_items.append(item)
            
            if len(news_items) >= limit:
                break
    
    return news_items


def get_company_news(ticker: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    智能获取新闻：自动识别是公司股票还是市场指数（结构化输出）。
    - 公司股票：使用 API (yfinance, Finnhub, Alpha Vantage)
    - 市场指数：使用搜索策略获取宏观市场新闻
    """
    try:
        limit = max(1, safe_int(limit, 5) or 5)
    except Exception:
        limit = 5
    limit = max(1, min(limit, 20))
    # 🔍 关键判断：这是指数还是公司股票？
    if _is_market_index(ticker):
        # 优先用 alert_scheduler 的新闻抓取（含48h过滤）
        try:
            from backend.services.alert_scheduler import fetch_news_articles
            articles = fetch_news_articles(ticker)
            if articles:
                items: List[Dict[str, Any]] = []
                for a in articles:
                    title = a.get("title") or a.get("headline") or a.get("summary") or "No title"
                    snippet = a.get("summary") or a.get("description") or ""
                    if not _headline_is_useful(title, snippet):
                        continue
                    source = a.get("source") or a.get("publisher") or "Unknown"
                    published_at = a.get("published_at") or a.get("datetime") or a.get("providerPublishTime") or 0
                    url = a.get("url") or a.get("link") or ""
                    item = _build_news_item(
                        title=title,
                        source=source,
                        url=url,
                        published_at=published_at,
                        snippet=snippet,
                        ticker=ticker,
                        confidence=0.7,
                    )
                    if item:
                        items.append(item)
                    if len(items) >= limit:
                        break
                if items:
                    return items
        except Exception as e:
            logger.info("index news via alert_scheduler failed: %s", type(e).__name__)

        # 先试 yfinance 的新闻（部分指数也有）
        try:
            stock = yf.Ticker(ticker)
            news = stock.news
            if news:
                items = []
                for article in news:
                    title = article.get('title', 'No title')
                    snippet = article.get('summary') or article.get('description') or ""
                    if not _headline_is_useful(title, snippet):
                        continue
                    publisher = article.get('publisher', 'Unknown source')
                    pub_time = article.get('providerPublishTime', 0)
                    url = article.get('link') or article.get('url') or ''
                    item = _build_news_item(
                        title=title,
                        source=publisher,
                        url=url,
                        published_at=pub_time,
                        snippet=snippet,
                        ticker=ticker,
                        confidence=0.7,
                    )
                    if item:
                        items.append(item)
                    if len(items) >= limit:
                        break
                if items:
                    return items
        except Exception as e:
            logger.info("yfinance index news error: %s", type(e).__name__)

        # 再退回搜索策略
        return _get_index_news(ticker, limit=limit)
    
    # --- 以下是原有的公司新闻获取逻辑 ---
    
    # 方法1: yfinance
    try:
        stock = yf.Ticker(ticker)
        news = stock.news
        if news:
            items = []
            for article in news:
                # 非 dict 毒条目按条跳过，否则 .get 抛 AttributeError
                # 落进方法级 except，已收集的 items 全丢（同 R107）。
                if not isinstance(article, dict):
                    continue
                title = article.get('title', 'No title')
                snippet = article.get('summary') or article.get('description') or ""
                if not _headline_is_useful(title, snippet):
                    continue
                publisher = article.get('publisher', 'Unknown source')
                pub_time = article.get('providerPublishTime', 0)
                url = article.get('link') or article.get('url') or ''
                item = _build_news_item(
                    title=title,
                    source=publisher,
                    url=url,
                    published_at=pub_time,
                    snippet=snippet,
                    ticker=ticker,
                    confidence=0.7,
                )
                if item:
                    items.append(item)
                if len(items) >= limit:
                    break
            if items:
                return items
    except Exception as e:
        logger.info("yfinance company news error: %s", type(e).__name__)

    # 方法2: Finnhub
    if finnhub_client:
        try:
            logger.info("Trying Finnhub company news")
            to_date = date.today().strftime("%Y-%m-%d")
            from_date = (date.today() - timedelta(days=7)).strftime("%Y-%m-%d")
            news = finnhub_client.company_news(ticker, _from=from_date, to=to_date)
            if news:
                items = []
                for article in news:
                    # 非 dict 毒条目按条跳过（同方法1/R107）
                    if not isinstance(article, dict):
                        continue
                    title = article.get('headline', 'No title')
                    snippet = article.get('summary') or ""
                    if not _headline_is_useful(title, snippet):
                        continue
                    source = article.get('source', 'Unknown')
                    pub_time = article.get('datetime', 0)
                    url = article.get('url') or ''
                    item = _build_news_item(
                        title=title,
                        source=source,
                        url=url,
                        published_at=pub_time,
                        snippet=snippet,
                        ticker=ticker,
                        confidence=0.8,
                    )
                    if item:
                        items.append(item)
                    if len(items) >= limit:
                        break
                if items:
                    return items
        except Exception as e:
            logger.info("Finnhub news fetch failed: %s", type(e).__name__)

    # 方法3: Alpha Vantage
    try:
        logger.info("Trying Alpha Vantage company news")
        url = "https://www.alphavantage.co/query"
        params = {'function': 'NEWS_SENTIMENT', 'tickers': ticker, 'limit': limit, 'apikey': ALPHA_VANTAGE_API_KEY}
        response = _http_get(url, params=params, timeout=10)
        data = response.json()
        feed = data.get('feed')
        if isinstance(feed, list) and feed:
            items = []
            for article in feed:
                # 单条毒记录（非 dict / present-None 字段）按条跳过；
                # 否则落进方法级 except 会连已收集的 items 一起丢（同 R107）。
                if not isinstance(article, dict):
                    continue
                title = article.get('title') or 'No title'
                source = article.get('source') or 'Unknown'
                date_str = str(article.get('time_published') or '')[:8]
                if date_str:
                    date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
                snippet = article.get('summary') or ""
                if not _headline_is_useful(title, snippet):
                    continue
                url = article.get('url') or article.get('link') or ''
                item = _build_news_item(
                    title=title,
                    source=source,
                    url=url,
                    published_at=date_str,
                    snippet=snippet,
                    ticker=ticker,
                    confidence=0.8,
                )
                if item:
                    items.append(item)
                if len(items) >= limit:
                    break
            if items:
                return items
    except Exception as e:
        logger.info("Alpha Vantage news fetch failed: %s", type(e).__name__)
    
    # 方法4: 回退到公司特定搜索
    logger.info("Falling back to company news search")
    fallback_text = search(f"{ticker} company latest news stock")
    items = _build_search_news_items(fallback_text, limit=limit, max_age_days=7)
    if items:
        for item in items:
            if isinstance(item, dict):
                item.setdefault("ticker", ticker)
        return items
    return []


_RELIABILITY_DOMAIN_SCORE_HINTS: Dict[str, float] = {
    "sec.gov": 0.98,
    "reuters.com": 0.95,
    "bloomberg.com": 0.94,
    "wsj.com": 0.92,
    "ft.com": 0.90,
    "cnbc.com": 0.88,
    "marketwatch.com": 0.86,
    "finance.yahoo.com": 0.84,
    "nasdaq.com": 0.84,
    "investing.com": 0.80,
    "fool.com": 0.72,
    "seekingalpha.com": 0.74,
}

_RELIABILITY_SOURCE_SCORE_HINTS: Dict[str, float] = {
    "sec": 0.98,
    "reuters": 0.95,
    "bloomberg": 0.94,
    "wall street journal": 0.92,
    "wsj": 0.92,
    "financial times": 0.90,
    "cnbc": 0.88,
    "marketwatch": 0.86,
    "yahoo": 0.84,
    "nasdaq": 0.84,
    "investing": 0.80,
    "fool": 0.72,
    "seeking alpha": 0.74,
}


def score_news_source_reliability(source: str = "", url: str = "") -> Dict[str, Any]:
    """Rule-based source reliability score for a news item."""
    source_text = str(source or "").strip()
    domain = _domain_from_url(str(url or ""))
    score = 0.55
    reason = "default"

    if domain:
        for hint, hint_score in _RELIABILITY_DOMAIN_SCORE_HINTS.items():
            # 域名提示只认整域或 ".hint" 结尾的合法子域；
            # 裸子串匹配会让 sec.gov.evil.example / notsec.gov
            # 这类仿冒主机继承权威分。
            if domain == hint or domain.endswith("." + hint):
                score = hint_score
                reason = f"domain:{hint}"
                break

    if reason == "default" and source_text:
        lowered = source_text.lower()
        for hint, hint_score in _RELIABILITY_SOURCE_SCORE_HINTS.items():
            if len(hint) <= 3 and hint.isascii():
                # 短 hint 走非字母数字边界——"sec" 不能命中 "SecurityWeek"/
                # "Second"，否则非SEC来源继承 0.98 权威分（domain 侧已做
                # 整域/子域边界，source 侧对齐）。与 _keyword_match /
                # parse_operation._match_any 同一策略。
                pattern = r"(?<![a-zA-Z0-9])" + re.escape(hint) + r"(?![a-zA-Z0-9])"
                matched = re.search(pattern, lowered) is not None
            else:
                matched = hint in lowered
            if matched:
                score = hint_score
                reason = f"source:{hint}"
                break

    if score >= 0.9:
        tier = "high"
    elif score >= 0.8:
        tier = "medium_high"
    elif score >= 0.65:
        tier = "medium"
    else:
        tier = "low"

    return {
        "source": source_text,
        "url": url,
        "domain": domain,
        "reliability_score": round(float(score), 4),
        "reliability_tier": tier,
        "reason": reason,
    }


def get_event_calendar(ticker: str, days_ahead: int = 30) -> Dict[str, Any]:
    """Get upcoming earnings/dividend/macro events (free-first)."""
    today = datetime.now(UTC).date()
    days = max(1, min(safe_int(days_ahead, 30) or 30, 120))
    end_date = today + timedelta(days=days)
    result: Dict[str, Any] = {
        "ticker": str(ticker or "").upper(),
        "source": "yfinance+search",
        "as_of": datetime.now(UTC).isoformat(),
        "days_ahead": days,
        "earnings_events": [],
        "dividend_events": [],
        "macro_events": [],
        "error": None,
    }
    if not ticker:
        result["error"] = "ticker_required"
        return result

    try:
        stock = yf.Ticker(ticker)
        calendar_payload = getattr(stock, "calendar", None)
        if isinstance(calendar_payload, dict):
            for key, raw_value in calendar_payload.items():
                values = raw_value if isinstance(raw_value, list) else [raw_value]
                for item in values:
                    candidate = _to_date_candidate(item)
                    if not _within_window(candidate, today, end_date):
                        continue
                    key_text = str(key or "").lower()
                    event = {
                        "date": candidate.isoformat(),
                        "title": str(key or "calendar_event"),
                        "source": "yfinance_calendar",
                    }
                    if "earn" in key_text:
                        result["earnings_events"].append(event)
                    elif "dividend" in key_text or "ex-dividend" in key_text:
                        result["dividend_events"].append(event)

        earnings_dates = getattr(stock, "earnings_dates", None)
        if earnings_dates is not None and not getattr(earnings_dates, "empty", True):
            for idx, _row in earnings_dates.head(8).iterrows():
                candidate = _to_date_candidate(idx)
                if not _within_window(candidate, today, end_date):
                    continue
                result["earnings_events"].append(
                    {
                        "date": candidate.isoformat(),
                        "title": "Earnings Date",
                        "source": "yfinance_earnings_dates",
                    }
                )
    except Exception as e:
        logger.info("[News] get_event_calendar yfinance failed: %s", type(e).__name__)

    macro_query = (
        f"US economic calendar next {days} days CPI PCE FOMC NFP GDP release dates"
    )
    macro_keywords = ("fomc", "cpi", "pce", "nonfarm", "payroll", "gdp", "inflation")
    try:
        text = search(macro_query)
        if isinstance(text, str) and text.strip():
            lines = [line.strip("-• ").strip() for line in text.splitlines() if line.strip()]
            for line in lines[:40]:
                lowered = line.lower()
                if not any(k in lowered for k in macro_keywords):
                    continue
                candidate = None
                iso_match = re.search(r"(20\d{2}-\d{2}-\d{2})", line)
                if iso_match:
                    candidate = _to_date_candidate(iso_match.group(1))
                else:
                    md_match = re.search(
                        r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+20\d{2})",
                        line,
                        flags=re.IGNORECASE,
                    )
                    if md_match:
                        candidate = _to_date_candidate(md_match.group(1))

                if candidate and not _within_window(candidate, today, end_date):
                    continue

                result["macro_events"].append(
                    {
                        "date": candidate.isoformat() if candidate else None,
                        "title": line[:160],
                        "source": "search_macro_calendar",
                    }
                )
                if len(result["macro_events"]) >= 8:
                    break
    except Exception as e:
        logger.info("[News] get_event_calendar macro search failed: %s", type(e).__name__)

    if not result["macro_events"]:
        result["macro_events"] = [
            {"date": None, "title": "Monitor upcoming CPI release window", "source": "macro_watchlist"},
            {"date": None, "title": "Monitor upcoming FOMC decision window", "source": "macro_watchlist"},
            {"date": None, "title": "Monitor upcoming Nonfarm Payrolls release window", "source": "macro_watchlist"},
        ]

    def _dedupe_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        output = []
        for event in events:
            if not isinstance(event, dict):
                continue
            key = (event.get("date"), event.get("title"), event.get("source"))
            if key in seen:
                continue
            seen.add(key)
            output.append(event)
        output.sort(key=lambda item: str(item.get("date") or "9999-99-99"))
        return output

    result["earnings_events"] = _dedupe_events(result["earnings_events"])
    result["dividend_events"] = _dedupe_events(result["dividend_events"])
    result["macro_events"] = _dedupe_events(result["macro_events"])

    if not result["earnings_events"] and not result["dividend_events"] and not result["macro_events"]:
        result["error"] = "no_calendar_events"
    return result


def get_news_sentiment(ticker: str, limit: int = 5) -> str:
    """
    获取新闻情绪 (Alpha Vantage NEWS_SENTIMENT)
    """
    if not ticker:
        return "News Sentiment: ticker is required."

    if not ALPHA_VANTAGE_API_KEY:
        return "News Sentiment: ALPHA_VANTAGE_API_KEY not configured."

    try:
        url = "https://www.alphavantage.co/query"
        params = {
            'function': 'NEWS_SENTIMENT',
            'tickers': ticker,
            'limit': limit,
            'apikey': ALPHA_VANTAGE_API_KEY,
        }
        response = _http_get(url, params=params, timeout=10)
        data = response.json()

        if not data or 'feed' not in data or not data.get('feed'):
            if isinstance(data, dict):
                if data.get('Note'):
                    return f"News Sentiment: rate limited ({data.get('Note')})"
                if data.get('Information'):
                    return f"News Sentiment: {data.get('Information')}"
                if data.get('Error Message'):
                    return f"News Sentiment: {data.get('Error Message')}"
            return "News Sentiment: no data found."

        def _extract_sentiment(item: Dict[str, Any], symbol: str):
            symbol_upper = symbol.upper()
            raw_ts = item.get('ticker_sentiment') or []
            if not isinstance(raw_ts, (list, tuple)):
                raw_ts = []
            for ts in raw_ts:
                # 单条畸形记录跳过即可，不能让整个情绪结果变 fetch failed
                if not isinstance(ts, dict):
                    continue
                if str(ts.get('ticker') or '').upper() == symbol_upper:
                    return ts.get('ticker_sentiment_score'), ts.get('ticker_sentiment_label')
            return item.get('overall_sentiment_score'), item.get('overall_sentiment_label')

        feed_items = data.get('feed')
        if not isinstance(feed_items, list):
            feed_items = []
        lines = []
        scores: List[float] = []
        # limit 语义是"最多 limit 条有效输出"：先过滤后计数，否则毒记录
        # 会烧掉 [:limit] 的名额，其后好记录被切掉（同 R60 缺陷类）。
        for item in feed_items:
            if len(lines) >= limit:
                break
            # feed 里混入非 dict 条目/present-None 字段时按条跳过；
            # 否则单条毒记录会落进函数级 except，整批结果全丢。
            if not isinstance(item, dict):
                continue
            title = item.get('title') or 'No title'
            source = item.get('source') or 'Unknown'
            time_published = item.get('time_published') or ''
            date_str = str(time_published)[:8]
            if date_str and len(date_str) == 8:
                date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
            else:
                date_str = 'Unknown date'
            url = item.get('url') or item.get('link') or ''
            score, label = _extract_sentiment(item, ticker)
            sentiment_desc = "N/A"
            try:
                if score is not None:
                    score_val = safe_float(score)
                    if score_val is not None:
                        scores.append(score_val)
                        sentiment_desc = f"{label or 'Unknown'} ({score_val:.2f})"
                    elif label:
                        sentiment_desc = label
                elif label:
                    sentiment_desc = label
            except Exception:
                if label:
                    sentiment_desc = label

            headline = f"[{title}]({url})" if url else title
            lines.append(f"{len(lines) + 1}. [{date_str}] {headline} ({source}) 情绪: {sentiment_desc}")

        avg_text = ""
        if scores:
            avg_score = sum(scores) / len(scores)
            avg_text = f"\n平均情绪分数: {avg_score:.2f}"

        return f"News Sentiment ({ticker}):{avg_text}\n" + "\n".join(lines)
    except Exception as e:
        return "News Sentiment: fetch failed"


def get_market_news_headlines(limit: int = 5) -> str:
    """
    市场泛化新闻：不带 ticker 的情况，抓取全球/美股要闻。
    使用搜索聚合并提取编号行作为标题，否则返回简短提示。
    """
    # 0) 官方 RSS（Reuters/Bloomberg），优先 48h 内
    bloomberg_default_feeds = [
        "https://feeds.bloomberg.com/markets/news.rss",
        "https://feeds.bloomberg.com/technology/news.rss",
        "https://feeds.bloomberg.com/politics/news.rss",
        "https://feeds.bloomberg.com/wealth/news.rss",
        "https://feeds.bloomberg.com/pursuits/news.rss",
        "https://feeds.bloomberg.com/businessweek/news.rss",
        "https://feeds.bloomberg.com/industries/news.rss",
    ]
    market_default_feeds = [
        "https://feeds.marketwatch.com/marketwatch/topstories/",
        "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
        "https://seekingalpha.com/feed.xml",
    ]

    reuters_env = os.getenv("REUTERS_RSS_URLS", "").strip()
    reuters_feeds = [u.strip() for u in reuters_env.split(",") if u.strip()]

    bloomberg_env = os.getenv("BLOOMBERG_RSS_URLS", "").strip()
    bloomberg_env_feeds = [u.strip() for u in bloomberg_env.split(",") if u.strip()]
    if bloomberg_env_feeds:
        bloomberg_feeds = bloomberg_default_feeds + [
            u for u in bloomberg_env_feeds if u not in bloomberg_default_feeds
        ]
    else:
        bloomberg_feeds = bloomberg_default_feeds

    market_env = os.getenv("MARKET_NEWS_RSS_URLS", "").strip()
    market_env_feeds = [u.strip() for u in market_env.split(",") if u.strip()]
    if market_env_feeds:
        market_feeds = market_default_feeds + [
            u for u in market_env_feeds if u not in market_default_feeds
        ]
    else:
        market_feeds = market_default_feeds

    rss_feeds: List[str] = []
    seen_urls = set()
    for url in (bloomberg_feeds + market_feeds + reuters_feeds):
        if url and url not in seen_urls:
            seen_urls.add(url)
            rss_feeds.append(url)

    rss_lines, rss_ok = _fetch_rss_headlines(rss_feeds, limit=limit * 2, max_age_days=2)
    if rss_ok:
        return "最近48小时市场要闻(RSS):\n" + "\n".join(rss_lines[:limit])

    # 1) Finnhub 市场新闻（48h）
    finnhub_lines, finnhub_ok = _fetch_finnhub_market_news(limit=limit * 2, max_age_hours=48)
    if finnhub_ok:
        return "最近48小时市场要闻(Finnhub):\n" + "\n".join(finnhub_lines[:limit])

    # 2) 尝试用 alert_scheduler 的新闻抓取（已含48h过滤），优先指数与代表性ETF
    try:
        from backend.services.alert_scheduler import fetch_news_articles
        for idx_ticker in ["^GSPC", "^IXIC", "SPY", "QQQ", "DIA", "IWM"]:
            try:
                articles = fetch_news_articles(idx_ticker)
            except Exception as inner:
                logger.info("[MarketNews] fetch_news_articles failed: %s", type(inner).__name__)
                continue
            if articles:
                lines = []
                for a in articles:
                    title = a.get("title") or a.get("headline") or a.get("summary") or "No title"
                    snippet = a.get("summary") or a.get("description") or ""
                    if not _headline_is_useful(title, snippet):
                        continue
                    source = a.get("source") or a.get("publisher") or "Unknown"
                    published_at = a.get("published_at") or a.get("datetime") or a.get("providerPublishTime") or 0
                    if isinstance(published_at, str):
                        date_str = published_at.split("T")[0]
                    else:
                        # UTC 取日（同文件 568/978 行惯例），裸 fromtimestamp 按本地时区跨零点偏一天
                        date_str = datetime.fromtimestamp(published_at, tz=UTC).strftime("%Y-%m-%d") if published_at else "Recent"
                    url = a.get("url") or a.get("link") or ""
                    line = _format_headline_line(date_str, title, source, url, snippet)
                    lines.append(f"{len(lines) + 1}. {line}")
                    if len(lines) >= limit:
                        break
                if lines:
                    return "最近48小时市场要闻:\n" + "\n".join(lines)
    except Exception as e:
        logger.info("[MarketNews] fetch via alert_scheduler failed: %s", type(e).__name__)

    # 3) 搜索聚合兜底
    queries = [
        "global stock market breaking news today",
        "US stock market headlines today",
        "market moving news today equities"
    ]
    combined = []
    for q in queries:
        try:
            res = search(q)
            combined.append(res)
        except Exception as e:
            logger.info("[MarketNews] search failed: %s", type(e).__name__)
            continue
    if not combined:
        return "未能获取可靠的市场热点信息，请直接查看 Bloomberg/Reuters/WSJ 等权威来源。"
    
    text = "\n\n".join(combined)
    lines, has_recent = _format_search_news_items(text, limit=limit, max_age_days=3)
    if not has_recent:
        lines, has_recent = _format_search_news_items(text, limit=limit, max_age_days=7)

    if not has_recent:
        retry_queries = [
            "global stock market news last 24 hours",
            "US stock market headlines last 24 hours",
            "market moving news past week site:reuters.com",
        ]
        retry_combined = []
        for q in retry_queries:
            try:
                res = search(q)
                retry_combined.append(res)
            except Exception as e:
                logger.info("[MarketNews] retry search failed: %s", type(e).__name__)
                continue
        if retry_combined:
            retry_text = "\n\n".join(retry_combined)
            retry_lines, retry_recent = _format_search_news_items(retry_text, limit=limit, max_age_days=7)
            if retry_lines and retry_recent:
                return "最近市场热点(近7天):\n" + "\n".join(retry_lines)
            if retry_recent:
                lines = retry_lines
                has_recent = True

    if has_recent and lines:
        return "最近市场热点(近7天):\n" + "\n".join(lines)

    return "近7天内未检索到可靠市场热点，请直接查看 Bloomberg/Reuters/WSJ 等权威来源。"
# ============================================
# 其他工具函数（保持不变或稍作修改）
# ============================================
