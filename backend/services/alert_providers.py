"""Network-facing data providers for alert scheduling.

Extracted from alert_scheduler so scheduler modules stay focused on
run-loop/execution logic while fetch/cache helpers live here.
"""
from __future__ import annotations

import logging
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

def _positive_finite_float(value: object) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def _first_positive_finite(*values: object) -> Optional[float]:
    for value in values:
        parsed = _positive_finite_float(value)
        if parsed is not None:
            return parsed
    return None


# A lightweight data shape for the price provider result.
@dataclass
class PriceSnapshot:
    ticker: str
    price: Optional[float]
    change_percent: Optional[float]


def fetch_price_snapshot(ticker: str) -> Optional[PriceSnapshot]:
    """
    Lightweight price fetcher with multi-source free fallbacks (no API key required):
    浼樺厛鍏嶅皝閿佺殑 stooq锛屽啀灏濊瘯 yfinance/Yahoo銆?    """
    snap = _get_cached_snapshot(ticker)
    if snap:
        return snap

    fetchers = (
        _fetch_with_stooq,
        _fetch_with_yfinance,
        _fetch_with_yahoo_quote,
        _fetch_with_yahoo_chart,
    )

    for fetcher in fetchers:
        snapshot = fetcher(ticker)
        if snapshot:
            _set_cache_snapshot(ticker, snapshot)
            return snapshot
    return None


def _parse_pub_datetime(raw: Any) -> Optional[datetime]:
    """epoch 秒（int/float/数字串）或 ISO8601 串 → naive-UTC；解析失败返回 None。

    yfinance 旧版给 epoch（providerPublishTime），新版给 ISO 串（content.pubDate），
    两种都须与 cutoff/lookback 的 naive-UTC 基准一致（审计 C3）。
    """
    if raw is None:
        return None
    try:
        return datetime.fromtimestamp(float(raw), tz=timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError, OSError, OverflowError):
        pass
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc)
        return dt.replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def fetch_news_articles(ticker: str) -> List[Dict]:
    """
    Fetch recent news for ticker. Uses yfinance news; filters to last 48h and attaches related tickers if provided.
    """
    articles: List[Dict] = []
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=48)
    ticker_up = ticker.upper()

    def _add_article(title: str, url: str, source: str, published_at: datetime, related: List[str] | None = None):
        if not isinstance(published_at, datetime) or published_at < cutoff:
            return
        articles.append(
            {
                "title": str(title or "")[:512],
                "url": str(url or "")[:2048],
                "source": str(source or "")[:128],
                "published_at": published_at,
                "related_tickers": [
                    r.strip().upper()[:20]
                    for r in (related or [])[:50]
                    if isinstance(r, str) and r.strip()
                ],
            }
        )

    try:
        import yfinance as yf  # type: ignore

        t = yf.Ticker(ticker)
        news = getattr(t, "news", []) or []
        for item in news:
            if not isinstance(item, dict):
                continue
            # yfinance >=0.2.5x 返回 Yahoo ncp 流结构：title/pubDate/url 嵌在
            # item["content"] 下，顶层旧字段全部为空 → 旧解析逐条丢弃、主路径
            # 静默失效。兼容新旧两种结构。
            content = item.get("content") if isinstance(item.get("content"), dict) else {}
            canonical_url = content.get("canonicalUrl") if isinstance(content.get("canonicalUrl"), dict) else {}
            click_url = content.get("clickThroughUrl") if isinstance(content.get("clickThroughUrl"), dict) else {}
            provider = content.get("provider") if isinstance(content.get("provider"), dict) else {}
            title = item.get("title") or content.get("title") or ""
            link = (
                item.get("link")
                or item.get("url")
                or canonical_url.get("url")
                or click_url.get("url")
            )
            pub_ts = (
                item.get("providerPublishTime")
                or item.get("pubDate")
                or content.get("pubDate")
            )
            pub_dt = _parse_pub_datetime(pub_ts)
            if not pub_dt or pub_dt < cutoff:
                continue
            related = item.get("relatedTickers") or item.get("tickers") or []
            source = (
                item.get("publisher")
                or item.get("source")
                or provider.get("displayName")
                or ""
            )
            _add_article(title, link, source, pub_dt, related)
    except Exception as e:
        logger.info("[NewsFetcher] yfinance news failed: %s", type(e).__name__)

    # Finnhub fallback
    if not articles:
        key = os.getenv("FINNHUB_API_KEY")
        if key:
            try:
                import requests  # type: ignore

                to_date = datetime.now(timezone.utc).date()
                from_date = to_date - timedelta(days=2)
                url = "https://finnhub.io/api/v1/company-news"
                params = {
                    "symbol": ticker_up,
                    "from": from_date.isoformat(),
                    "to": to_date.isoformat(),
                    "token": key,
                }
                resp = requests.get(url, params=params, timeout=8)
                if resp.status_code == 200:
                    for item in resp.json() or []:
                        if not isinstance(item, dict):
                            continue
                        title = item.get("headline", "")
                        link = item.get("url", "")
                        source = item.get("source", "")
                        ts = item.get("datetime")
                        pub_dt = (
                            datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
                            if ts else None
                        )
                        related = item.get("related", "").split(",") if item.get("related") else [ticker_up]
                        _add_article(title, link, source, pub_dt, related)
            except Exception as e:
                logger.info("[NewsFetcher] finnhub news failed: %s", type(e).__name__)

    # Alpha Vantage fallback
    if not articles:
        key = os.getenv("ALPHA_VANTAGE_API_KEY")
        if key:
            try:
                import requests  # type: ignore

                url = "https://www.alphavantage.co/query"
                params = {"function": "NEWS_SENTIMENT", "tickers": ticker_up, "limit": 10, "apikey": key}
                resp = requests.get(url, params=params, timeout=8)
                data = resp.json()
                feed = data.get("feed") or []
                for item in feed:
                    if not isinstance(item, dict):
                        continue
                    title = item.get("title", "")
                    link = item.get("url") or item.get("link", "")
                    source = item.get("source", "")
                    ts_str = item.get("time_published", "")
                    pub_dt = None
                    if ts_str:
                        try:
                            pub_dt = datetime.strptime(ts_str[:12], "%Y%m%d%H%M")
                        except Exception:
                            pub_dt = None
                    related = item.get("ticker_sentiment", [])
                    rel_codes = [r.get("ticker") for r in related if isinstance(r, dict) and r.get("ticker")]
                    _add_article(title, link, source, pub_dt, rel_codes or [ticker_up])
            except Exception as e:
                logger.info("[NewsFetcher] alpha vantage news failed: %s", type(e).__name__)

    return articles


def _fetch_with_yfinance(ticker: str) -> Optional[PriceSnapshot]:
    try:
        import yfinance as yf  # type: ignore

        t = yf.Ticker(ticker)
        info = getattr(t, "fast_info", {}) or {}
        price = _first_positive_finite(
            info.get("last_price"), info.get("last_close"), info.get("lastClose")
        )
        if price is None:
            return None
        prev_close = _first_positive_finite(
            info.get("previous_close"), info.get("previousClose"), info.get("regularMarketPreviousClose")
        )

        change_percent = None
        if prev_close is not None:
            change_percent = (price - prev_close) / prev_close * 100.0

        return PriceSnapshot(ticker=ticker, price=price, change_percent=change_percent)
    except Exception as exc:
        logger.debug('yfinance quote fetch failed')
        return None


def _fetch_with_yahoo_quote(ticker: str) -> Optional[PriceSnapshot]:
    """
    Hit Yahoo quote endpoint (no key). Provides regularMarketPrice + regularMarketPreviousClose.
    """
    try:
        import requests  # type: ignore

        url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={ticker}"
        headers = {"User-Agent": "Mozilla/5.0 (FinSightBot)"}
        resp = requests.get(url, timeout=8, headers=headers)
        if resp.status_code != 200:
            return None
        data = resp.json().get("quoteResponse", {}).get("result", [])
        if not data:
            return None
        item = data[0]
        price = _positive_finite_float(item.get("regularMarketPrice"))
        if price is None:
            return None
        prev_close = _positive_finite_float(item.get("regularMarketPreviousClose"))
        change_percent = None
        if prev_close is not None:
            change_percent = (price - prev_close) / prev_close * 100.0
        return PriceSnapshot(ticker=ticker, price=price, change_percent=change_percent)
    except Exception as exc:
        logger.debug('Yahoo quote fetch failed')
        return None


def _fetch_with_stooq(ticker: str) -> Optional[PriceSnapshot]:
    """
    Free source: stooq.pl (no key)。快照接口无昨收字段——此前用当日开盘
    近似日涨跌，隔夜跳空场景喂给告警阈值的 change_percent 严重失真
    （跳空 +6% 盘中平走会被算成 ~0% 而漏报）。改为另拉日线取真昨收；
    拉不到时 change_percent=None（调度器跳过本轮，优于错误基准触发）。
    """
    try:
        import csv
        import io

        import requests  # type: ignore

        # stooq ticker needs .us suffix for US stocks
        symbol = f"{ticker.lower()}.us"
        url = f"https://stooq.pl/q/l/?s={symbol}&f=sd2t2ohlcv&h&e=json"
        resp = requests.get(url, timeout=8)
        if resp.status_code != 200:
            return None
        data = (resp.json() or {}).get("symbols") or []
        if not data:
            return None
        item = data[0]
        close = item.get("close")
        if close in (None, "N/D"):
            return None
        price = _positive_finite_float(close)
        if price is None:
            return None

        prev = None
        try:
            end = datetime.now(timezone.utc).date()
            start = end - timedelta(days=10)
            hist_url = f"https://stooq.pl/q/d/l/?s={symbol}&d1={start:%Y%m%d}&d2={end:%Y%m%d}&i=d"
            hist = requests.get(hist_url, timeout=8)
            if hist.status_code == 200 and hist.text:
                today_iso = end.isoformat()
                closes = []
                for row in csv.DictReader(io.StringIO(hist.text)):
                    row_date = str(row.get("Date") or row.get("Data") or "").strip()
                    raw = row.get("Close") or row.get("Zamkniecie")
                    value = _positive_finite_float(raw)
                    if value is not None and row_date and row_date < today_iso:
                        closes.append(value)
                if closes:
                    prev = closes[-1]
        except Exception as exc:
            logger.debug('Stooq history fetch failed')
            prev = None

        change_percent = None
        if prev:
            change_percent = (price - prev) / prev * 100.0
        return PriceSnapshot(ticker=ticker, price=price, change_percent=change_percent)
    except Exception as exc:
        logger.debug('Stooq quote fetch failed')
        return None


def _fetch_with_yahoo_chart(ticker: str) -> Optional[PriceSnapshot]:
    """
    Use Yahoo chart endpoint (2d range, 1d interval) to derive last close and previous close.
    """
    try:
        import requests  # type: ignore

        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=2d&interval=1d"
        resp = requests.get(url, timeout=5)
        if resp.status_code != 200:
            return None
        chart = resp.json().get("chart", {})
        result = (chart.get("result") or [None])[0] or {}
        closes = (result.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
        if len(closes) < 2:
            return None
        prev_close = _positive_finite_float(closes[-2])
        price = _positive_finite_float(closes[-1])
        if price is None or prev_close is None:
            return None
        change_percent = (price - prev_close) / prev_close * 100.0
        return PriceSnapshot(ticker=ticker, price=price, change_percent=change_percent)
    except Exception as exc:
        logger.debug('Yahoo chart fetch failed')
        return None


# --- Simple in-process cache to reduce rate hitting free sources ---
_PRICE_CACHE: Dict[str, Tuple[PriceSnapshot, float]] = {}
_CACHE_TTL = 300  # seconds


def _get_cached_snapshot(ticker: str) -> Optional[PriceSnapshot]:
    now = time.time()
    snap_ts = _PRICE_CACHE.get(ticker.upper())
    if not snap_ts:
        return None
    snap, ts = snap_ts
    try:
        age = now - float(ts)
    except (TypeError, ValueError, OverflowError):
        age = math.inf
    if math.isfinite(age) and 0 <= age <= _CACHE_TTL:
        return snap
    _PRICE_CACHE.pop(ticker.upper(), None)
    return None


def _set_cache_snapshot(ticker: str, snapshot: PriceSnapshot) -> None:
    _PRICE_CACHE[ticker.upper()] = (snapshot, time.time())
