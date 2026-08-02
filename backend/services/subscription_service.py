#!/usr/bin/env python3
"""
订阅管理服务
管理用户的股票订阅和提醒
"""

import logging

logger = logging.getLogger(__name__)

# -*- coding: utf-8 -*-


import json
import math
import os
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from pathlib import Path
import re
from uuid import uuid4

from backend.utils.env_config import env_int
from backend.utils.quote import safe_int
from backend.utils.strict_json import json_load_strict

# 订阅数据存储文件
SUBSCRIPTIONS_FILE = Path(__file__).parent.parent.parent / "data" / "subscriptions.json"
ALERT_FAILURE_LIMIT = env_int("ALERT_FAILURE_LIMIT", 3, minimum=1)
ALERT_EVENTS_PER_SUB = env_int("ALERT_EVENTS_PER_SUB", 30, minimum=1)
ALERT_EVENTS_TTL_DAYS = env_int("ALERT_EVENTS_TTL_DAYS", 7, minimum=1)
EMAIL_REGEX = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
RISK_THRESHOLD_ALLOWED = {"low", "medium", "high", "critical"}
ALERT_MODE_ALLOWED = {"price_change_pct", "price_target"}
DIRECTION_ALLOWED = {"above", "below"}
_SUBSCRIPTIONS_LOCK = threading.RLock()
_MAX_ALERT_EVENT_TITLE_LENGTH = 512
_MAX_ALERT_EVENT_MESSAGE_LENGTH = 4096
_MAX_ALERT_EVENT_METADATA_BYTES = 16 * 1024


def _reject_non_finite_json(value: str) -> None:
    raise ValueError(f"non-finite JSON value: {value}")


def _finite_optional_number(value: object, *, field: str) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be finite") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number


class SubscriptionLimitExceeded(Exception):
    def __init__(self, *, limit: int, current: int) -> None:
        super().__init__("subscription limit exceeded")
        self.limit = limit
        self.current = current


class SubscriptionService:
    """订阅管理服务"""
    
    def __init__(self):
        self.subscriptions_file = SUBSCRIPTIONS_FILE
        self._lock = _SUBSCRIPTIONS_LOCK
        self.subscriptions_file.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._load_subscriptions()
    
    def _load_subscriptions(self):
        """加载订阅数据"""
        if self.subscriptions_file.exists():
            try:
                with open(self.subscriptions_file, 'r', encoding='utf-8') as f:
                    subscriptions = json_load_strict(f)
                if not isinstance(subscriptions, dict):
                    raise ValueError("subscriptions payload must be a JSON object")
                if any(
                    not isinstance(items, list)
                    or any(not isinstance(item, dict) for item in items)
                    for items in subscriptions.values()
                ):
                    raise ValueError(
                        "subscription entries must be lists of JSON objects"
                    )
                self.subscriptions = subscriptions
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as e:
                backup_path = self.subscriptions_file.with_name(
                    f"{self.subscriptions_file.name}.{uuid4().hex}.corrupt"
                )
                os.replace(self.subscriptions_file, backup_path)
                logger.warning(
                    "Subscription data was corrupt and moved to a backup (%s)",
                    type(e).__name__,
                )
                self.subscriptions = {}
        else:
            self.subscriptions = {}
        self._backfill_subscription_defaults()

    def _normalize_risk_threshold(self, value: Optional[str]) -> str:
        if value is None:
            return "high"
        normalized = str(value).strip().lower()
        if normalized not in RISK_THRESHOLD_ALLOWED:
            return "high"
        return normalized

    def _normalize_alert_mode(self, value: Optional[str]) -> str:
        normalized = str(value or "price_change_pct").strip().lower()
        if normalized not in ALERT_MODE_ALLOWED:
            return "price_change_pct"
        return normalized

    def _normalize_direction(self, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip().lower()
        if normalized not in DIRECTION_ALLOWED:
            return None
        return normalized

    def _backfill_subscription_defaults(self) -> None:
        changed = False
        if not isinstance(self.subscriptions, dict):
            self.subscriptions = {}
            return

        for email, subs in self.subscriptions.items():
            if not isinstance(subs, list):
                continue
            for sub in subs:
                if not isinstance(sub, dict):
                    continue
                if sub.get("email") != email:
                    sub["email"] = email
                    changed = True
                normalized_threshold = self._normalize_risk_threshold(sub.get("risk_threshold"))
                if sub.get("risk_threshold") != normalized_threshold:
                    sub["risk_threshold"] = normalized_threshold
                    changed = True
                normalized_mode = self._normalize_alert_mode(sub.get("alert_mode"))
                if sub.get("alert_mode") != normalized_mode:
                    sub["alert_mode"] = normalized_mode
                    changed = True
                if "price_target" not in sub:
                    sub["price_target"] = None
                    changed = True
                normalized_direction = self._normalize_direction(sub.get("direction"))
                if sub.get("direction") != normalized_direction:
                    sub["direction"] = normalized_direction
                    changed = True
                if "price_target_fired" not in sub:
                    sub["price_target_fired"] = False
                    changed = True
                if "last_risk_at" not in sub:
                    sub["last_risk_at"] = None
                    changed = True
                if "recent_events" not in sub or not isinstance(sub.get("recent_events"), list):
                    sub["recent_events"] = []
                    changed = True
                else:
                    pruned = self._prune_recent_events(sub.get("recent_events") or [])
                    if pruned != sub.get("recent_events"):
                        sub["recent_events"] = pruned
                        changed = True

        if changed:
            self._save_subscriptions()
    
    def _save_subscriptions(self):
        """保存订阅数据"""
        try:
            with self._lock:
                fd, temp_path = tempfile.mkstemp(
                    prefix=f"{self.subscriptions_file.name}.",
                    suffix=".tmp",
                    dir=str(self.subscriptions_file.parent),
                    text=True,
                )
                try:
                    with os.fdopen(fd, 'w', encoding='utf-8') as f:
                        json.dump(
                            self.subscriptions,
                            f,
                            indent=2,
                            ensure_ascii=False,
                            allow_nan=False,
                        )
                        f.flush()
                        os.fsync(f.fileno())
                    os.replace(temp_path, self.subscriptions_file)
                finally:
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
        except Exception as e:
            logger.error("Failed to save subscription data (%s)", type(e).__name__)
            raise

    @staticmethod
    def _parse_iso(value: Optional[str]) -> Optional[datetime]:
        if not value or not isinstance(value, str):
            return None
        text = value.strip()
        if not text:
            return None
        try:
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            return datetime.fromisoformat(text)
        except Exception:
            return None

    @staticmethod
    def _to_utc_naive(value: Optional[datetime]) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _normalize_event_metadata(value: object) -> Dict:
        metadata = value if isinstance(value, dict) else {}
        try:
            size = len(
                json.dumps(
                    metadata,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
            )
        except (TypeError, ValueError):
            return {}
        return metadata if size <= _MAX_ALERT_EVENT_METADATA_BYTES else {}

    def _prune_recent_events(self, events: List[Dict]) -> List[Dict]:
        if not isinstance(events, list):
            return []
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=max(1, ALERT_EVENTS_TTL_DAYS))
        keep: List[Dict] = []
        for item in events:
            if not isinstance(item, dict):
                continue
            triggered_at = self._to_utc_naive(self._parse_iso(str(item.get("triggered_at") or "")))
            if triggered_at is None:
                continue
            if triggered_at < cutoff:
                continue
            keep.append({
                "id": str(item.get("id") or "")[:64],
                "email": str(item.get("email") or "")[:320],
                "ticker": str(item.get("ticker") or "").strip().upper()[:20],
                "event_type": str(item.get("event_type") or "unknown")[:64],
                "severity": str(item.get("severity") or "medium")[:32],
                "title": str(item.get("title") or "")[:_MAX_ALERT_EVENT_TITLE_LENGTH],
                "message": str(item.get("message") or "")[:_MAX_ALERT_EVENT_MESSAGE_LENGTH],
                "triggered_at": str(item.get("triggered_at") or "")[:64],
                "metadata": self._normalize_event_metadata(item.get("metadata")),
            })
        keep.sort(key=lambda item: str(item.get("triggered_at") or ""), reverse=True)
        return keep[: max(1, ALERT_EVENTS_PER_SUB)]
    
    def subscribe(
        self,
        email: str,
        ticker: str,
        alert_types: List[str] = None,
        price_threshold: Optional[float] = None,
        alert_mode: Optional[str] = "price_change_pct",
        price_target: Optional[float] = None,
        direction: Optional[str] = None,
        risk_threshold: Optional[str] = "high",
        max_subscriptions: Optional[int] = None,
    ) -> bool:
        """
        订阅股票提醒
        
        Args:
            email: 用户邮箱
            ticker: 股票代码
            alert_types: 提醒类型列表（price_change, news, report）
            price_threshold: 价格变动阈值（百分比）
            
        Returns:
            是否订阅成功
        """
        if alert_types is None:
            alert_types = ["price_change", "news"]
        price_threshold = _finite_optional_number(
            price_threshold,
            field="price_threshold",
        )
        price_target = _finite_optional_number(price_target, field="price_target")
        normalized_risk_threshold = self._normalize_risk_threshold(risk_threshold)
        normalized_alert_mode = self._normalize_alert_mode(alert_mode)
        normalized_direction = self._normalize_direction(direction)

        if not self.is_valid_email(email):
            logger.info("Invalid email address rejected")
            return False

        with self._lock:
            self._load_subscriptions()
            if email not in self.subscriptions:
                self.subscriptions[email] = []

            # 检查是否已订阅
            for sub in self.subscriptions[email]:
                if sub['ticker'] == ticker:
                    # 更新现有订阅
                    sub['alert_types'] = alert_types
                    sub['price_threshold'] = price_threshold
                    sub['alert_mode'] = normalized_alert_mode
                    sub['price_target'] = price_target
                    sub['direction'] = normalized_direction
                    sub['risk_threshold'] = normalized_risk_threshold
                    sub['price_target_fired'] = False
                    sub['updated_at'] = datetime.now().isoformat()
                    if "recent_events" not in sub or not isinstance(sub.get("recent_events"), list):
                        sub["recent_events"] = []
                    # 重新启用并清理失败状态
                    sub['disabled'] = False
                    sub['alert_failures'] = 0
                    sub['last_alert_error'] = None
                    sub['last_alert_error_at'] = None
                    self._save_subscriptions()
                    return True

            if max_subscriptions is not None and max_subscriptions >= 0:
                current = len(self.subscriptions[email])
                if current >= max_subscriptions:
                    raise SubscriptionLimitExceeded(
                        limit=max_subscriptions,
                        current=current,
                    )

            # 添加新订阅
            subscription = {
                "email": email,
                "ticker": ticker,
                "alert_types": alert_types,
                "price_threshold": price_threshold,
                "alert_mode": normalized_alert_mode,
                "price_target": price_target,
                "direction": normalized_direction,
                "risk_threshold": normalized_risk_threshold,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "last_alert_at": None,
                "last_news_at": None,
                "last_risk_at": None,
                "last_alert_attempt_at": None,
                "last_alert_error": None,
                "last_alert_error_at": None,
                "alert_failures": 0,
                "disabled": False,
                "price_target_fired": False,
                "recent_events": [],
            }

            self.subscriptions[email].append(subscription)
            self._save_subscriptions()
            logger.info("Subscription created")
            return True

    def is_valid_email(self, email: str) -> bool:
        """Basic email format validation."""
        if not email or "@" not in email:
            return False
        return bool(EMAIL_REGEX.match(email))
    
    def unsubscribe(self, email: str, ticker: Optional[str] = None) -> bool:
        """
        取消订阅
        
        Args:
            email: 用户邮箱
            ticker: 股票代码（如果为 None，取消所有订阅）
            
        Returns:
            是否取消成功
        """
        with self._lock:
            self._load_subscriptions()
            if email not in self.subscriptions:
                return False
            if ticker is None:
                # 取消所有订阅
                del self.subscriptions[email]
            else:
                # 取消特定股票的订阅
                self.subscriptions[email] = [
                    sub for sub in self.subscriptions[email]
                    if sub['ticker'] != ticker
                ]

                # 如果该邮箱没有其他订阅，删除邮箱记录
                if not self.subscriptions[email]:
                    del self.subscriptions[email]

            self._save_subscriptions()
            logger.info("Subscription removed")
            return True
    
    def get_subscriptions(self, email: Optional[str] = None, *, allow_all: bool = False) -> List[Dict]:
        """
        获取订阅列表
        
        Args:
            email: 用户邮箱（如果为 None，返回所有订阅）
            
        Returns:
            订阅列表
        """
        if email is None:
            if not allow_all:
                return []
            # 返回所有订阅
            with self._lock:
                self._load_subscriptions()
                all_subs = []
                for email_key, subs in self.subscriptions.items():
                    all_subs.extend(subs)
                return all_subs
        else:
            with self._lock:
                self._load_subscriptions()
                return list(self.subscriptions.get(email, []))

    def get_subscribers_for_ticker(self, ticker: str) -> List[Dict]:
        """
        获取订阅特定股票的所有用户

        Args:
            ticker: 股票代码

        Returns:
            订阅列表
        """
        subscribers = []
        with self._lock:
            self._load_subscriptions()
            for email, subs in self.subscriptions.items():
                for sub in subs:
                    if sub['ticker'] == ticker:
                        subscribers.append(sub)
        return subscribers

    def update_last_alert(self, email: str, ticker: str):
        """更新最后提醒时间"""
        with self._lock:
            self._load_subscriptions()
            if email in self.subscriptions:
                for sub in self.subscriptions[email]:
                    if sub['ticker'] == ticker:
                        sub['last_alert_at'] = datetime.now().isoformat()
                        self._save_subscriptions()
                        break

    def record_alert_attempt(self, email: str, ticker: str, success: bool, error: Optional[str] = None, disable: bool = False, is_transient_error: bool = False):
        """Record alert delivery attempt and optionally disable subscription."""
        with self._lock:
            self._load_subscriptions()
            if email in self.subscriptions:
                for sub in self.subscriptions[email]:
                    if sub['ticker'] == ticker:
                        now = datetime.now().isoformat()
                        sub['last_alert_attempt_at'] = now
                        if success:
                            sub['last_alert_at'] = now
                            sub['alert_failures'] = 0
                            sub['last_alert_error'] = None
                            sub['last_alert_error_at'] = None
                            sub['disabled'] = False
                        else:
                            if not is_transient_error:
                                failure_count = max(0, safe_int(sub.get('alert_failures'), 0) or 0)
                                sub['alert_failures'] = failure_count + 1

                            if error == "invalid_email":
                                stored_error = "invalid_email"
                            elif is_transient_error:
                                stored_error = "transient_delivery_error"
                            else:
                                stored_error = "delivery_error"
                            sub['last_alert_error'] = stored_error
                            sub['last_alert_error_at'] = now

                            # Only disable if explicitly requested OR failure limit reached (for non-transient errors)
                            should_disable = disable or (not is_transient_error and sub['alert_failures'] >= ALERT_FAILURE_LIMIT)
                            if should_disable:
                                sub['disabled'] = True

                        self._save_subscriptions()
                        break

    def update_last_news(self, email: str, ticker: str):
        """更新最后新闻提醒时间

        写 naive-UTC（审计 C3）：该值在 NewsAlertScheduler.run_once 里与文章
        published_at（naive-UTC）直接比较做去重，两侧必须同基准；
        裸 datetime.now() 是本地时区，中国区会把新文章误判为已推送过。
        """
        with self._lock:
            self._load_subscriptions()
            if email in self.subscriptions:
                for sub in self.subscriptions[email]:
                    if sub['ticker'] == ticker:
                        sub['last_news_at'] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
                        self._save_subscriptions()
                        break

    def update_last_risk(self, email: str, ticker: str):
        """Update last risk alert timestamp."""
        with self._lock:
            self._load_subscriptions()
            if email in self.subscriptions:
                for sub in self.subscriptions[email]:
                    if sub['ticker'] == ticker:
                        sub['last_risk_at'] = datetime.now().isoformat()
                        self._save_subscriptions()
                        break

    def set_price_target_fired(self, email: str, ticker: str) -> bool:
        """Mark one-shot target alert as fired."""
        ticker_norm = str(ticker or "").strip().upper()
        with self._lock:
            self._load_subscriptions()
            if email not in self.subscriptions:
                return False
            for sub in self.subscriptions[email]:
                if str(sub.get("ticker") or "").strip().upper() == ticker_norm:
                    sub["price_target_fired"] = True
                    sub["updated_at"] = datetime.now().isoformat()
                    self._save_subscriptions()
                    return True
            return False

    def toggle_subscription(self, email: str, ticker: str, enabled: bool) -> bool:
        """
        启用或禁用订阅

        Args:
            email: 用户邮箱
            ticker: 股票代码
            enabled: True=启用, False=禁用

        Returns:
            是否操作成功
        """
        with self._lock:
            self._load_subscriptions()
            if email not in self.subscriptions:
                return False

            for sub in self.subscriptions[email]:
                if sub['ticker'] == ticker:
                    sub['disabled'] = not enabled
                    if enabled:
                        # 启用时重置失败计数
                        sub['alert_failures'] = 0
                        sub['last_alert_error'] = None
                        sub['last_alert_error_at'] = None
                    sub['updated_at'] = datetime.now().isoformat()
                    self._save_subscriptions()
                    logger.info("Subscription status updated for single ticker")
                    return True

            return False

    def record_alert_event(
        self,
        email: str,
        ticker: str,
        event_type: str,
        *,
        severity: str = "medium",
        title: str = "",
        message: str = "",
        metadata: Optional[Dict] = None,
        triggered_at: Optional[str] = None,
    ) -> bool:
        """Append one alert trigger event into subscription.recent_events."""
        updated = False
        now_iso = triggered_at or datetime.now(timezone.utc).isoformat()
        normalized_ticker = str(ticker or "").strip().upper()

        with self._lock:
            self._load_subscriptions()
            if email not in self.subscriptions:
                return False

            for sub in self.subscriptions[email]:
                if str(sub.get("ticker") or "").strip().upper() != normalized_ticker:
                    continue

                events = sub.get("recent_events")
                if not isinstance(events, list):
                    events = []

                event_type_text = str(event_type or "unknown")[:64]
                severity_text = str(severity or "medium")[:32]
                title_text = str(title or "").strip() or f"{normalized_ticker} {event_type_text}"
                message_text = str(message or "").strip()
                event_metadata = self._normalize_event_metadata(metadata)

                payload = {
                    "id": f"ae_{uuid4().hex[:12]}",
                    "email": email,
                    "ticker": normalized_ticker,
                    "event_type": event_type_text,
                    "severity": severity_text,
                    "title": title_text[:_MAX_ALERT_EVENT_TITLE_LENGTH],
                    "message": message_text[:_MAX_ALERT_EVENT_MESSAGE_LENGTH],
                    "triggered_at": str(now_iso)[:64],
                    "metadata": event_metadata,
                }
                events.insert(0, payload)
                sub["recent_events"] = self._prune_recent_events(events)
                updated = True
                break

            if updated:
                self._save_subscriptions()
        return updated

    def list_alert_events(
        self,
        email: str,
        *,
        limit: int = 50,
        since: Optional[str] = None,
    ) -> List[Dict]:
        """Aggregate recent alert events for one user across all subscriptions."""
        with self._lock:
            self._load_subscriptions()
            subscriptions = list(self.subscriptions.get(email, []))
        if not isinstance(subscriptions, list):
            return []

        since_dt = self._to_utc_naive(self._parse_iso(since)) if since else None
        events: List[Dict] = []
        for sub in subscriptions:
            if not isinstance(sub, dict):
                continue
            for item in self._prune_recent_events(sub.get("recent_events") or []):
                triggered = self._to_utc_naive(self._parse_iso(str(item.get("triggered_at") or "")))
                if since_dt and triggered and triggered < since_dt:
                    continue
                events.append(item)

        events.sort(key=lambda item: str(item.get("triggered_at") or ""), reverse=True)
        return events[: max(1, safe_int(limit, 50) or 50)]



# 全局实例
_subscription_service = None

def get_subscription_service() -> SubscriptionService:
    """获取订阅服务实例（单例模式）"""
    global _subscription_service
    if _subscription_service is None:
        _subscription_service = SubscriptionService()
    return _subscription_service
