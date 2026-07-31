"""
Minimal alert scheduling skeleton for price_change rule.

This keeps the logic small and testable:
- Pull subscriptions from SubscriptionService.
- For entries that opt into price_change and have a price_threshold, fetch a price snapshot.
- When absolute change_percent meets/exceeds the threshold, trigger EmailService.send_stock_alert
  and record last_alert_at.

This module is intentionally framework-light so it can later be wired to
APScheduler/Celery/async cron as needed.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple
import time
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime, timedelta, timezone

from backend.agents.risk_agent import RiskAgent, RiskLevel
from backend.services.subscription_service import SubscriptionService
from backend.services.email_service import EmailService

logger = logging.getLogger(__name__)

_DELIVERY_ERROR_TYPES = {"transient", "permanent", "unknown"}
_TICKER_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.^=-")


def _normalize_delivery_error_type(value: object) -> str:
    normalized = str(value or "unknown").strip().lower()
    return normalized if normalized in _DELIVERY_ERROR_TYPES else "unknown"


def _subscription_ticker(subscription: object) -> Optional[str]:
    if not isinstance(subscription, dict):
        return None
    raw = subscription.get("ticker")
    if not isinstance(raw, str):
        return None
    ticker = raw.strip().upper()
    if not ticker or len(ticker) > 20:
        return None
    if ticker[0] not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789^":
        return None
    return ticker if all(char in _TICKER_CHARS for char in ticker) else None


def _positive_env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


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


class PriceChangeScheduler:
    """
    Execute price alerts once.
    Supports:
    - price_change_pct: abs(change_percent) threshold with cooldown.
    - price_target: one-shot absolute price target trigger.
    """

    def __init__(
        self,
        subscription_service: SubscriptionService,
        email_service: EmailService,
        price_fetcher: Callable[[str], Optional[PriceSnapshot]],
    ) -> None:
        self.subscription_service = subscription_service
        self.email_service = email_service
        self.price_fetcher = price_fetcher

    @staticmethod
    def _parse_dt(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            return None

    def _is_cooling_down(self, sub: dict) -> bool:
        cooldown_minutes = _positive_env_int("PRICE_ALERT_COOLDOWN_MINUTES", 60)
        last_alert_at = self._parse_dt(sub.get("last_alert_at"))
        if last_alert_at is None:
            return False
        return (datetime.now(last_alert_at.tzinfo) - last_alert_at) < timedelta(minutes=cooldown_minutes)

    def run_once(self) -> List[Dict]:
        sent: List[Dict] = []
        subscriptions = self.subscription_service.get_subscriptions(allow_all=True)
        checked = 0

        for sub in subscriptions:
            ticker = _subscription_ticker(sub)
            if ticker is None:
                continue
            if ticker != sub.get("ticker"):
                sub = {**sub, "ticker": ticker}
            if sub.get("disabled"):
                continue
            alert_types = sub.get("alert_types") or []
            if "price_change" not in alert_types:
                continue
            checked += 1

            alert_mode = str(sub.get("alert_mode") or "price_change_pct").strip().lower()
            try:
                snapshot = self.price_fetcher(sub["ticker"])
            except Exception as exc:
                logger.warning(
                    "Price fetch failed for ticker=%s (%s)",
                    sub["ticker"],
                    type(exc).__name__,
                )
                continue
            if snapshot is None:
                continue
            try:
                snapshot_price = float(snapshot.price)
            except (TypeError, ValueError, OverflowError):
                continue
            if not math.isfinite(snapshot_price) or snapshot_price <= 0:
                continue
            snapshot.price = snapshot_price

            threshold_payload: Optional[float] = None
            price_target_payload: Optional[float] = None
            direction_payload: Optional[str] = None

            if alert_mode == "price_target":
                if bool(sub.get("price_target_fired")):
                    continue
                price_target = sub.get("price_target")
                if price_target is None or snapshot.price is None:
                    continue
                try:
                    price_target_payload = float(price_target)
                except Exception:
                    continue
                if not math.isfinite(price_target_payload) or price_target_payload <= 0:
                    continue
                direction_payload = str(sub.get("direction") or "").strip().lower()
                if direction_payload == "below":
                    triggered = snapshot.price <= price_target_payload
                else:
                    direction_payload = "above"
                    triggered = snapshot.price >= price_target_payload
                if not triggered:
                    continue
                message = (
                    f"{sub['ticker']} reached target price {price_target_payload:.2f} "
                    f"({direction_payload}), current={snapshot.price:.2f}."
                )
            else:
                threshold = sub.get("price_threshold")
                if threshold is None:
                    continue
                try:
                    threshold_payload = float(threshold)
                except Exception:
                    continue
                if not math.isfinite(threshold_payload) or threshold_payload <= 0:
                    continue
                if self._is_cooling_down(sub):
                    continue
                if snapshot.change_percent is None:
                    continue
                try:
                    change_percent = float(snapshot.change_percent)
                except (TypeError, ValueError, OverflowError):
                    continue
                if not math.isfinite(change_percent):
                    continue
                snapshot.change_percent = change_percent
                if abs(snapshot.change_percent) < threshold_payload:
                    continue
                message = (
                    f"{sub['ticker']} price moved {snapshot.change_percent:+.2f}% "
                    f"(threshold {threshold_payload:.2f}%)."
                )

            if not self.subscription_service.is_valid_email(sub.get("email", "")):
                self.subscription_service.record_alert_attempt(
                    sub["email"],
                    sub["ticker"],
                    success=False,
                    error="invalid_email",
                    disable=True,
                )
                continue

            try:
                result = self.email_service.send_stock_alert(
                    to_email=sub["email"],
                    ticker=sub["ticker"],
                    alert_type="price_target" if alert_mode == "price_target" else "price_change",
                    message=message,
                    current_price=snapshot.price,
                    change_percent=snapshot.change_percent,
                )
            except Exception as exc:
                logger.warning(
                    "Email send raised for ticker=%s (%s)",
                    sub["ticker"],
                    type(exc).__name__,
                )
                self.subscription_service.record_alert_attempt(
                    sub["email"],
                    sub["ticker"],
                    success=False,
                    error="send_failed",
                )
                continue
            if isinstance(result, tuple):
                success, error_type, error_msg = result
            else:
                success, error_type, error_msg = result, "unknown", None
            error_type = _normalize_delivery_error_type(error_type)

            if not success:
                logger.warning("Email send failed for ticker=%s (%s)", sub["ticker"], error_type)
                self.subscription_service.record_alert_attempt(
                    sub["email"],
                    sub["ticker"],
                    success=False,
                    error=error_msg or "send_failed",
                    is_transient_error=(error_type == "transient"),
                )
                continue

            self.subscription_service.record_alert_attempt(sub["email"], sub["ticker"], success=True)
            if alert_mode == "price_target":
                self.subscription_service.set_price_target_fired(sub["email"], sub["ticker"])

            severity = "medium"
            if alert_mode != "price_target" and threshold_payload is not None and snapshot.change_percent is not None:
                severity = "high" if abs(snapshot.change_percent) >= threshold_payload * 2 else "medium"

            self.subscription_service.record_alert_event(
                sub["email"],
                sub["ticker"],
                "price_target" if alert_mode == "price_target" else "price_change",
                severity=severity,
                title=(
                    f"{sub['ticker']} 到价触发 {snapshot.price:.2f}"
                    if alert_mode == "price_target"
                    else f"{sub['ticker']} 价格异动 {snapshot.change_percent:+.2f}%"
                ),
                message=message,
                metadata={
                    "alert_mode": alert_mode,
                    "threshold": threshold_payload,
                    "price_target": price_target_payload,
                    "direction": direction_payload,
                    "change_percent": snapshot.change_percent,
                    "current_price": snapshot.price,
                },
            )

            sent.append(
                {
                    "email": sub["email"],
                    "ticker": sub["ticker"],
                    "alert_mode": alert_mode,
                    "change_percent": snapshot.change_percent,
                    "threshold": threshold_payload,
                    "price_target": price_target_payload,
                    "message": message,
                }
            )

        logger.info(
            "price_change run completed: checked=%s, sent=%s",
            checked,
            len(sent),
        )
        return sent


class NewsAlertScheduler:
    """
    News alert: fetch recent articles and notify when related to subscribed ticker.
    """

    def __init__(
        self,
        subscription_service: SubscriptionService,
        email_service: EmailService,
        news_fetcher: Callable[[str], List[Dict]],
    ) -> None:
        self.subscription_service = subscription_service
        self.email_service = email_service
        self.news_fetcher = news_fetcher

    def run_once(self) -> List[Dict]:
        sent: List[Dict] = []
        subs = self.subscription_service.get_subscriptions(allow_all=True)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        lookback = now - timedelta(hours=24)
        checked = 0

        for sub in subs:
            ticker = _subscription_ticker(sub)
            if ticker is None:
                continue
            if ticker != sub.get("ticker"):
                sub = {**sub, "ticker": ticker}
            if sub.get("disabled"):
                continue
            alert_types = sub.get("alert_types") or []
            if "news" not in alert_types:
                continue
            checked += 1

            last_news_at = sub.get("last_news_at")
            try:
                last_dt = datetime.fromisoformat(str(last_news_at)) if last_news_at else None
            except (TypeError, ValueError):
                last_dt = None
            # 统一 naive-UTC 基准（审计 C3）：与 lookback / 文章 published_at 同基准比较
            if last_dt is not None and last_dt.tzinfo is not None:
                last_dt = last_dt.astimezone(timezone.utc).replace(tzinfo=None)

            try:
                articles = self.news_fetcher(sub["ticker"])
            except Exception as exc:
                logger.warning(
                    "News fetch failed for ticker=%s (%s)",
                    sub["ticker"],
                    type(exc).__name__,
                )
                continue
            if not articles:
                continue

            # 鐩稿叧鎬э細浼樺厛 related_tickers 鍛戒腑锛屽叾娆℃爣棰樺寘鍚?TICKER
            related: List[Dict] = []
            for art in articles:
                if not isinstance(art, dict):
                    continue
                pub_dt = art.get("published_at")
                if isinstance(pub_dt, str):
                    try:
                        pub_dt = datetime.fromisoformat(pub_dt)
                    except Exception:
                        pub_dt = None
                if not isinstance(pub_dt, datetime):
                    continue
                # 带时区的 aware 值归一到 naive-UTC，避免与 naive 的 lookback 比较抛 TypeError
                if pub_dt.tzinfo is not None:
                    pub_dt = pub_dt.astimezone(timezone.utc).replace(tzinfo=None)
                if pub_dt < lookback:
                    continue
                if last_dt and pub_dt <= last_dt:
                    continue

                raw_related = art.get("related_tickers") or []
                rel = {
                    str(value).strip().upper()
                    for value in raw_related
                    if isinstance(value, str) and value.strip()
                } if isinstance(raw_related, (list, tuple, set)) else set()
                title = str(art.get("title") or "")[:512]
                if sub["ticker"].upper() in rel or sub["ticker"].upper() in title.upper():
                    related.append({
                        "title": title,
                        "source": str(art.get("source") or "")[:128],
                        "url": str(art.get("url") or "")[:2048],
                        "published_at": pub_dt,
                    })

            if not related:
                continue

            # Keep only the latest three related articles for one digest email.
            related = sorted(related, key=lambda x: x["published_at"], reverse=True)[:3]
            lines = []
            for art in related:
                ts = art["published_at"].strftime("%Y-%m-%d %H:%M UTC")
                lines.append(f"[{ts}] {art.get('title','')} ({art.get('source','')}) {art.get('url','')}")
            message = "\n".join(lines)

            try:
                result = self.email_service.send_stock_alert(
                    to_email=sub["email"],
                    ticker=sub["ticker"],
                    alert_type="news",
                    message=message,
                    current_price=None,
                    change_percent=None,
                )
            except Exception as exc:
                logger.warning(
                    "News email send raised for ticker=%s (%s)",
                    sub["ticker"],
                    type(exc).__name__,
                )
                self.subscription_service.record_alert_attempt(
                    sub["email"],
                    sub["ticker"],
                    success=False,
                    error="send_failed",
                )
                continue
            
            if isinstance(result, tuple):
                success, error_type, error_msg = result
            else:
                success, error_type, error_msg = result, 'unknown', None
            error_type = _normalize_delivery_error_type(error_type)

            # Only update last_news_at if email was actually sent
            if not success:
                logger.warning("News email send failed for ticker=%s (%s)", sub["ticker"], error_type)
                self.subscription_service.record_alert_attempt(
                    sub["email"],
                    sub["ticker"],
                    success=False,
                    error=error_msg or "send_failed",
                    is_transient_error=(error_type == 'transient')
                )
                continue
            self.subscription_service.update_last_news(sub["email"], sub["ticker"])
            self.subscription_service.record_alert_event(
                sub["email"],
                sub["ticker"],
                "news",
                severity="high" if len(related) >= 2 else "medium",
                title=f"{sub['ticker']} 鐩稿叧鏂伴椈瑙﹀彂 ({len(related)} 鏉?",
                message=message,
                metadata={
                    "article_count": len(related),
                    "latest_article": related[0].get("title") if related else "",
                },
            )

            sent.append(
                {
                    "email": sub["email"],
                    "ticker": sub["ticker"],
                    "articles": lines,
                }
            )

        logger.info(
            "news run completed: checked=%s, sent=%s",
            checked,
            len(sent),
        )
        return sent


class RiskAlertScheduler:
    """Execute risk alerts once with dependency injection."""

    _RISK_LEVEL_ORDER: dict[RiskLevel, int] = {
        RiskLevel.LOW: 1,
        RiskLevel.MEDIUM: 2,
        RiskLevel.HIGH: 3,
        RiskLevel.CRITICAL: 4,
    }

    def __init__(
        self,
        subscription_service: SubscriptionService,
        email_service: EmailService,
        price_fetcher: Callable[[str], Optional[PriceSnapshot]],
    ) -> None:
        self.subscription_service = subscription_service
        self.email_service = email_service
        self.price_fetcher = price_fetcher

    @staticmethod
    def _parse_dt(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            return None

    @classmethod
    def _normalize_threshold(cls, value: Optional[str]) -> RiskLevel:
        raw = str(value or "high").strip().lower()
        try:
            return RiskLevel(raw)
        except Exception:
            return RiskLevel.HIGH

    @classmethod
    def _meets_threshold(cls, actual: RiskLevel, threshold: RiskLevel) -> bool:
        return cls._RISK_LEVEL_ORDER[actual] >= cls._RISK_LEVEL_ORDER[threshold]

    def _is_cooling_down(self, sub: dict) -> bool:
        cooldown_minutes = _positive_env_int("RISK_ALERT_COOLDOWN_MINUTES", 180)
        last_risk_at = self._parse_dt(sub.get("last_risk_at"))
        if last_risk_at is None:
            return False
        return (datetime.now(last_risk_at.tzinfo) - last_risk_at) < timedelta(minutes=cooldown_minutes)

    def run_once(self) -> List[Dict]:
        sent: List[Dict] = []
        subscriptions = self.subscription_service.get_subscriptions(allow_all=True)
        checked = 0

        for sub in subscriptions:
            ticker = _subscription_ticker(sub)
            if ticker is None:
                continue
            if ticker != sub.get("ticker"):
                sub = {**sub, "ticker": ticker}
            if sub.get("disabled"):
                continue

            alert_types = sub.get("alert_types") or []
            if "risk" not in alert_types:
                continue
            checked += 1

            if self._is_cooling_down(sub):
                continue

            try:
                snapshot = self.price_fetcher(sub["ticker"])
            except Exception as exc:
                logger.warning(
                    "Risk price fetch failed for ticker=%s (%s)",
                    sub["ticker"],
                    type(exc).__name__,
                )
                continue
            if snapshot is None:
                continue

            assessment = RiskAgent.evaluate_ticker_risk_lightweight(
                str(sub["ticker"]).strip().upper(),
                snapshot,
            )
            threshold = self._normalize_threshold(sub.get("risk_threshold"))

            if not self._meets_threshold(assessment.risk_level, threshold):
                continue

            message = (
                f"{assessment.ticker} risk score {assessment.risk_score:.1f}/100, "
                f"level {assessment.risk_level.value}. {assessment.summary}"
            )

            if not self.subscription_service.is_valid_email(sub.get("email", "")):
                self.subscription_service.record_alert_attempt(
                    sub["email"],
                    sub["ticker"],
                    success=False,
                    error="invalid_email",
                    disable=True,
                )
                continue

            try:
                result = self.email_service.send_stock_alert(
                    to_email=sub["email"],
                    ticker=sub["ticker"],
                    alert_type="risk",
                    message=message,
                    current_price=snapshot.price,
                    change_percent=snapshot.change_percent,
                )
            except Exception as exc:
                logger.warning(
                    "Risk email send raised for ticker=%s (%s)",
                    sub["ticker"],
                    type(exc).__name__,
                )
                self.subscription_service.record_alert_attempt(
                    sub["email"],
                    sub["ticker"],
                    success=False,
                    error="send_failed",
                )
                continue

            if isinstance(result, tuple):
                success, error_type, error_msg = result
            else:
                success, error_type, error_msg = result, "unknown", None
            error_type = _normalize_delivery_error_type(error_type)

            if not success:
                logger.warning("Risk email send failed for ticker=%s (%s)", sub["ticker"], error_type)
                self.subscription_service.record_alert_attempt(
                    sub["email"],
                    sub["ticker"],
                    success=False,
                    error=error_msg or "send_failed",
                    is_transient_error=(error_type == "transient"),
                )
                continue

            self.subscription_service.record_alert_attempt(sub["email"], sub["ticker"], success=True)
            self.subscription_service.update_last_risk(sub["email"], sub["ticker"])
            self.subscription_service.record_alert_event(
                sub["email"],
                sub["ticker"],
                "risk",
                severity=assessment.risk_level.value,
                title=f"{assessment.ticker} 椋庨櫓绛夌骇 {assessment.risk_level.value}",
                message=message,
                metadata={
                    "risk_score": assessment.risk_score,
                    "risk_level": assessment.risk_level.value,
                    "risk_threshold": threshold.value,
                    "change_percent": snapshot.change_percent,
                },
            )

            sent.append(
                {
                    "email": sub["email"],
                    "ticker": sub["ticker"],
                    "risk_score": assessment.risk_score,
                    "risk_level": assessment.risk_level.value,
                    "risk_threshold": threshold.value,
                    "message": message,
                }
            )

        logger.info("risk run completed: checked=%s, sent=%s", checked, len(sent))
        return sent


# --- Convenience helpers ---

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
        logger.info("[NewsFetcher] yfinance news failed for %s: %s", ticker, type(e).__name__)

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
                logger.info("[NewsFetcher] finnhub news failed for %s: %s", ticker, type(e).__name__)

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
                logger.info("[NewsFetcher] alpha vantage news failed for %s: %s", ticker, type(e).__name__)

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
        logger.debug("yfinance quote fetch failed for %s: %s", ticker, type(exc).__name__)
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
        logger.debug("Yahoo quote fetch failed for %s: %s", ticker, type(exc).__name__)
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
            logger.debug("Stooq history fetch failed for %s: %s", ticker, type(exc).__name__)
            prev = None

        change_percent = None
        if prev:
            change_percent = (price - prev) / prev * 100.0
        return PriceSnapshot(ticker=ticker, price=price, change_percent=change_percent)
    except Exception as exc:
        logger.debug("Stooq quote fetch failed for %s: %s", ticker, type(exc).__name__)
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
        logger.debug("Yahoo chart fetch failed for %s: %s", ticker, type(exc).__name__)
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


def run_price_change_cycle() -> List[Dict]:
    """
    One-shot price_change sweep using default services and fetcher.
    This can be hooked to APScheduler/cron; kept synchronous for simplicity.
    """
    from backend.services.subscription_service import get_subscription_service
    from backend.services.email_service import get_email_service

    scheduler = PriceChangeScheduler(
        subscription_service=get_subscription_service(),
        email_service=get_email_service(),
        price_fetcher=fetch_price_snapshot,
    )
    res = scheduler.run_once()
    return res


def run_news_alert_cycle() -> List[Dict]:
    """
    One-shot news sweep using default services and fetcher.
    """
    from backend.services.subscription_service import get_subscription_service
    from backend.services.email_service import get_email_service

    scheduler = NewsAlertScheduler(
        subscription_service=get_subscription_service(),
        email_service=get_email_service(),
        news_fetcher=fetch_news_articles,
    )
    res = scheduler.run_once()
    return res


def run_risk_alert_cycle() -> List[Dict]:
    """One-shot risk sweep using default services and price fetcher."""
    from backend.services.subscription_service import get_subscription_service
    from backend.services.email_service import get_email_service

    scheduler = RiskAlertScheduler(
        subscription_service=get_subscription_service(),
        email_service=get_email_service(),
        price_fetcher=fetch_price_snapshot,
    )
    res = scheduler.run_once()
    return res


LOG_DIR = Path(os.getenv("ALERT_LOG_DIR", Path(__file__).resolve().parent.parent.parent / "logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)

def _get_logger() -> logging.Logger:
    logger = logging.getLogger("alerts")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    logger.propagate = False
    log_path = LOG_DIR / "alerts.log"
    handler = RotatingFileHandler(log_path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    if str(os.getenv("ALERT_LOG_STDOUT_ENABLED", "false")).strip().lower() in {"1", "true", "yes", "on"}:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
    return logger

logger = _get_logger()
