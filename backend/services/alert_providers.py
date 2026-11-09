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
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from backend.utils.quote import safe_float

logger = logging.getLogger(__name__)

def _positive_finite_float(value: object) -> Optional[float]:
    if isinstance(value, bool):
        return None
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
    if snap is not None and snap.change_percent is not None:
        return snap

    fetchers = (
        _fetch_with_stooq,
        _fetch_with_yfinance,
        _fetch_with_yahoo_quote,
        _fetch_with_yahoo_chart,
    )

    price_only_snapshot = None
    for fetcher in fetchers:
        snapshot = fetcher(ticker)
        if snapshot:
            if str(getattr(snapshot, "ticker", "") or "").strip().upper() != ticker.strip().upper():
                continue
            price = _positive_finite_float(snapshot.price)
            if price is None:
                continue
            snapshot.price = price
            snapshot.change_percent = safe_float(snapshot.change_percent)
            if snapshot.change_percent is None:
                price_only_snapshot = price_only_snapshot or snapshot
                continue
            _set_cache_snapshot(ticker, snapshot)
            return snapshot

    if price_only_snapshot is not None:
        _set_cache_snapshot(ticker, price_only_snapshot)
        return price_only_snapshot

    if snap is not None:
        return snap

    # 四个源全试过仍为空：此前这里毫无痕迹地返回 None，调用方（告警循环）
    # 于是把它当成"阈值没突破"跳过，一轮下来"无告警"与"报价源全挂"同形。
    # debug 级也不留（各 fetcher 只打各自的 debug），故这里补一条 warning。
    logger.warning('price snapshot unavailable for alert cycle')
    return None


def _parse_pub_datetime(raw: Any) -> Optional[datetime]:
    """epoch 秒（int/float/数字串）或 ISO8601 串 → naive-UTC；解析失败返回 None。

    yfinance 旧版给 epoch（providerPublishTime），新版给 ISO 串（content.pubDate），
    两种都须与 cutoff/lookback 的 naive-UTC 基准一致（审计 C3）。
    """
    if raw is None or isinstance(raw, bool):
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
    except (TypeError, ValueError, OverflowError):
        return None


def fetch_news_articles(ticker: str, *, lookback_hours: int = 48) -> List[Dict]:
    """
    Fetch recent news for ticker, defaulting to the last 48h, with related tickers if provided.
    """
    articles: List[Dict] = []
    if lookback_hours <= 0:
        return articles
    ticker = ticker.strip().upper()
    if not ticker:
        return articles
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=lookback_hours)
    ticker_up = ticker

    def _add_article(title: str, url: str, source: str, published_at: datetime, related: List[str] | None = None):
        if not isinstance(title, str) or not title.strip():
            return
        if (
            not isinstance(published_at, datetime) or published_at < cutoff
            or published_at > datetime.now(timezone.utc).replace(tzinfo=None)
        ):
            return
        if isinstance(related, str):
            related = related.split(",")
        elif not isinstance(related, list):
            related = []
        related_tickers = [
            r.strip().upper()[:20]
            for r in related[:50]
            if isinstance(r, str) and r.strip()
        ]
        if related_tickers and ticker_up not in related_tickers:
            return
        articles.append(
            {
                "title": str(title or "")[:512],
                "url": str(url or "")[:2048],
                "source": str(source or "")[:128],
                "published_at": published_at,
                "related_tickers": related_tickers,
            }
        )

    try:
        import yfinance as yf  # type: ignore

        t = yf.Ticker(ticker)
        news = getattr(t, "news", []) or []
        for item in news:
            if (not isinstance(item, dict) or item.get("error") or item.get("success") is False
                or str(item.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
                continue
            # yfinance >=0.2.5x 返回 Yahoo ncp 流结构：title/pubDate/url 嵌在
            # item["content"] 下，顶层旧字段全部为空 → 旧解析逐条丢弃、主路径
            # 静默失效。兼容新旧两种结构。
            content = item.get("content") if isinstance(item.get("content"), dict) else {}
            if (content.get("error") or content.get("success") is False
                or str(content.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
                continue
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
                        if (not isinstance(item, dict) or item.get("error") or item.get("success") is False
                            or str(item.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
                            continue
                        title = item.get("headline", "")
                        link = item.get("url", "")
                        source = item.get("source", "")
                        ts = item.get("datetime")
                        pub_dt = _parse_pub_datetime(ts)
                        related = item.get("related") or [ticker_up]
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
                if resp.status_code != 200:
                    return articles
                data = resp.json()
                if (not isinstance(data, dict) or data.get("error") or data.get("success") is False
                    or str(data.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
                    return articles
                feed = data.get("feed") or []
                for item in feed:
                    if (not isinstance(item, dict) or item.get("error") or item.get("success") is False
                        or str(item.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
                        continue
                    title = item.get("title", "")
                    link = item.get("url") or item.get("link", "")
                    source = item.get("source", "")
                    ts_str = item.get("time_published", "")
                    pub_dt = None
                    if ts_str:
                        try:
                            timestamp_format = {12: "%Y%m%d%H%M", 14: "%Y%m%d%H%M%S", 15: "%Y%m%dT%H%M%S"}[len(ts_str)]
                            pub_dt = datetime.strptime(ts_str, timestamp_format)
                        except (TypeError, ValueError, KeyError):
                            pub_dt = None
                    related = item.get("ticker_sentiment", [])
                    if not isinstance(related, list):
                        related = []
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
        if (info.get("error") or info.get("success") is False
            or str(info.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
            return None
        if any(value is not None and str(value).strip().upper() != ticker.strip().upper()
               for value in (info.get("ticker"), info.get("symbol"))):
            return None
        price = _first_positive_finite(
            info.get("last_price"), info.get("lastPrice"), info.get("last_close"), info.get("lastClose")
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
        quote_response = resp.json().get("quoteResponse", {})
        if (not isinstance(quote_response, dict) or quote_response.get("error")
            or quote_response.get("success") is False
            or str(quote_response.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
            return None
        data = quote_response.get("result", [])
        if not data:
            return None
        item = next((
            entry for entry in data if isinstance(entry, dict)
            and not entry.get("error") and entry.get("success") is not False
            and str(entry.get("status") or "").strip().lower() not in {"error", "failed", "unavailable"}
            and str(entry.get("symbol") or "").strip().upper() == ticker.strip().upper()
        ), None)
        if item is None:
            return None
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
        payload = resp.json() or {}
        if (not isinstance(payload, dict) or payload.get("error") or payload.get("success") is False
            or str(payload.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
            return None
        data = payload.get("symbols") or []
        if not data:
            return None
        item = data[0]
        if (item.get("error") or item.get("success") is False
            or str(item.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
            return None
        if str(item.get("symbol") or "").strip().lower() != symbol:
            return None
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
                quote_iso = datetime.fromisoformat(str(item.get("date") or end.isoformat())).date().isoformat()
                closes = []
                for row in csv.DictReader(io.StringIO(hist.text)):
                    row_date = str(row.get("Date") or row.get("Data") or "").strip()
                    try:
                        row_date = date.fromisoformat(row_date).isoformat()
                    except ValueError:
                        continue
                    raw = row.get("Close") or row.get("Zamkniecie")
                    value = _positive_finite_float(raw)
                    if value is not None and row_date and row_date < quote_iso:
                        closes.append((row_date, value))
                if closes:
                    prev = max(closes, key=lambda row: row[0])[1]
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
        if (chart.get("error") or chart.get("success") is False
            or str(chart.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
            return None
        result = (chart.get("result") or [None])[0] or {}
        if (result.get("error") or result.get("success") is False
            or str(result.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
            return None
        if str((result.get("meta") or {}).get("symbol") or "").strip().upper() != ticker.strip().upper():
            return None
        closes = (result.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
        closes = [close for close in closes if close is not None]
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
    price = _positive_finite_float(getattr(snap, "price", None))
    change_percent = safe_float(getattr(snap, "change_percent", None))
    if (
        math.isfinite(age) and 0 <= age <= _CACHE_TTL
        and str(getattr(snap, "ticker", "") or "").strip().upper() == ticker.strip().upper()
        and price is not None
        and (snap.change_percent is None or change_percent is not None)
    ):
        snap.price = price
        snap.change_percent = change_percent
        return snap
    _PRICE_CACHE.pop(ticker.upper(), None)
    return None


def _set_cache_snapshot(ticker: str, snapshot: PriceSnapshot) -> None:
    _PRICE_CACHE[ticker.upper()] = (snapshot, time.time())
