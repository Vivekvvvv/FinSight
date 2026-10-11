import logging
import re
import time
from datetime import datetime, timedelta, date
from typing import List, Dict, Any

import yfinance as yf

from .env import ALPHA_VANTAGE_API_KEY, finnhub_client
from .http import _http_get
from .search import search
from ._item import iter_dict_items, num_or, text_or
from backend.utils.quote import safe_int

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
                for a in iter_dict_items(articles):
                    # 非 dict 毒条目由 iter_dict_items 按条跳过（同 R107-R110）
                    title = text_or(a.get("title")) or text_or(a.get("headline")) or text_or(a.get("summary")) or "No title"
                    snippet = text_or(a.get("summary")) or text_or(a.get("description"))
                    if not _headline_is_useful(title, snippet):
                        continue
                    source = text_or(a.get("source")) or text_or(a.get("publisher")) or "Unknown"
                    published_at = a.get("published_at") or a.get("datetime") or a.get("providerPublishTime") or 0
                    url = text_or(a.get("url")) or text_or(a.get("link"))
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
                for article in iter_dict_items(news):
                    # 非 dict 毒条目由 iter_dict_items 按条跳过（同 R107）
                    title = text_or(article.get('title')) or 'No title'
                    snippet = text_or(article.get('summary')) or text_or(article.get('description'))
                    if not _headline_is_useful(title, snippet):
                        continue
                    publisher = text_or(article.get('publisher')) or 'Unknown source'
                    pub_time = num_or(article.get('providerPublishTime'))
                    url = text_or(article.get('link')) or text_or(article.get('url'))
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
            for article in iter_dict_items(news):
                # 非 dict 毒条目由 iter_dict_items 按条跳过（同 R107）
                title = text_or(article.get('title')) or 'No title'
                snippet = text_or(article.get('summary')) or text_or(article.get('description'))
                if not _headline_is_useful(title, snippet):
                    continue
                publisher = text_or(article.get('publisher')) or 'Unknown source'
                pub_time = num_or(article.get('providerPublishTime'))
                url = text_or(article.get('link')) or text_or(article.get('url'))
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
                for article in iter_dict_items(news):
                    # 非 dict 毒条目由 iter_dict_items 按条跳过（同方法1/R107）
                    title = text_or(article.get('headline')) or 'No title'
                    snippet = text_or(article.get('summary'))
                    if not _headline_is_useful(title, snippet):
                        continue
                    source = text_or(article.get('source')) or 'Unknown'
                    pub_time = num_or(article.get('datetime'))
                    url = text_or(article.get('url'))
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
            for article in iter_dict_items(feed):
                # 单条毒记录由 iter_dict_items 按条跳过（同 R107）
                title = text_or(article.get('title')) or 'No title'
                source = text_or(article.get('source')) or 'Unknown'
                date_str = str(article.get('time_published') or '')[:8]
                if date_str:
                    date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
                snippet = text_or(article.get('summary'))
                if not _headline_is_useful(title, snippet):
                    continue
                url = text_or(article.get('url')) or text_or(article.get('link'))
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
        for item in iter_dict_items(items):
            item.setdefault("ticker", ticker)
        return items
    return []


from backend.tools.news_market_providers import (
    _RELIABILITY_DOMAIN_SCORE_HINTS,
    _RELIABILITY_SOURCE_SCORE_HINTS,
    get_event_calendar,
    get_market_news_headlines,
    get_news_sentiment,
    score_news_source_reliability,
)

# ============================================
# 其他工具函数（保持不变或稍作修改）
# ============================================
