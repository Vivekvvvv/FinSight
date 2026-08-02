# -*- coding: utf-8 -*-
"""
Memory Service - 用户记忆与画像管理
负责持久化用户偏好、投资风格、历史关注等长期记忆
"""

import logging
import threading
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import json
import os
import re
from uuid import uuid4

from backend.utils.strict_json import json_load_strict
from backend.utils.quote import safe_int

logger = logging.getLogger(__name__)
_USER_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# 模块级锁：MemoryService 在 main.py / graph/store.py / what_changed.py 等处
# 各自实例化但共享同一 data/memory 目录，锁必须跨实例生效。
_PROFILE_LOCK = threading.RLock()


def _reject_non_finite_json(value: str) -> None:
    raise ValueError(f"non-finite JSON value: {value}")


class WatchlistLimitExceeded(Exception):
    def __init__(self, *, limit: int, current: int) -> None:
        super().__init__("watchlist limit exceeded")
        self.limit = limit
        self.current = current


@dataclass
class UserProfile:
    """用户画像"""
    user_id: str
    risk_tolerance: str = "medium"  # low, medium, high
    investment_style: str = "balanced"  # conservative, balanced, aggressive
    watchlist: List[str] = field(default_factory=list)
    # Watchlist 2.0 — 每个 ticker 的额外元信息 (name / tags / note).
    # 保留 watchlist: List[str] 用于向后兼容; meta 单独存储,旧调用方无感知。
    watchlist_meta: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    preferences: Dict[str, Any] = field(default_factory=dict)
    last_active: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "risk_tolerance": self.risk_tolerance,
            "investment_style": self.investment_style,
            "watchlist": self.watchlist,
            "watchlist_meta": self.watchlist_meta,
            "preferences": self.preferences,
            "last_active": self.last_active
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserProfile':
        meta = data.get("watchlist_meta") or {}
        return cls(
            user_id=data.get("user_id", "default"),
            risk_tolerance=data.get("risk_tolerance", "medium"),
            investment_style=data.get("investment_style", "balanced"),
            watchlist=data.get("watchlist", []),
            watchlist_meta=meta if isinstance(meta, dict) else {},
            preferences=data.get("preferences", {}),
            last_active=data.get("last_active", datetime.now().isoformat())
        )

class MemoryService:
    """
    记忆服务
    目前使用简单的 JSON 文件存储，后续可迁移至 Redis/Postgres
    """

    def __init__(self, storage_path: str = "data/memory"):
        self.storage_path = storage_path
        if not os.path.exists(storage_path):
            os.makedirs(storage_path)

    def _normalize_user_id(self, user_id: str) -> str:
        normalized = str(user_id or "").strip()
        if not _USER_ID_PATTERN.fullmatch(normalized):
            raise ValueError("invalid user_id: only [A-Za-z0-9._-], length 1-64")
        return normalized

    def _get_file_path(self, user_id: str) -> str:
        normalized_user_id = self._normalize_user_id(user_id)
        return os.path.join(self.storage_path, f"{normalized_user_id}.json")

    def get_user_profile(self, user_id: str) -> UserProfile:
        """获取用户画像，不存在则创建默认"""
        normalized_user_id = self._normalize_user_id(user_id)
        file_path = self._get_file_path(normalized_user_id)
        with _PROFILE_LOCK:
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json_load_strict(f)
                    if not isinstance(data, dict):
                        raise ValueError("profile payload must be a JSON object")
                    stored_user_id = str(data.get("user_id") or normalized_user_id).strip()
                    if stored_user_id != normalized_user_id:
                        raise ValueError("profile user_id does not match its storage key")
                    watchlist = data.get("watchlist", [])
                    if not isinstance(watchlist, list) or any(
                        not isinstance(ticker, str) for ticker in watchlist
                    ):
                        raise ValueError("profile watchlist must be a list of strings")
                    if not isinstance(data.get("watchlist_meta", {}), dict):
                        raise ValueError("profile watchlist_meta must be an object")
                    if not isinstance(data.get("preferences", {}), dict):
                        raise ValueError("profile preferences must be an object")
                    data["user_id"] = normalized_user_id
                    return UserProfile.from_dict(data)
                except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as e:
                    backup_path = f"{file_path}.{uuid4().hex}.corrupt"
                    os.replace(file_path, backup_path)
                    logger.warning(
                        "[MemoryService] Corrupt profile moved to backup (%s)",
                        type(e).__name__,
                    )
                    return UserProfile(user_id=normalized_user_id)
            else:
                return UserProfile(user_id=normalized_user_id)

    def update_user_profile(self, profile: UserProfile) -> bool:
        """更新用户画像"""
        file_path = self._get_file_path(profile.user_id)
        profile.last_active = datetime.now().isoformat()
        tmp_path = file_path + ".tmp"
        try:
            with _PROFILE_LOCK:
                with open(tmp_path, 'w', encoding='utf-8') as f:
                    json.dump(
                        profile.to_dict(),
                        f,
                        indent=2,
                        ensure_ascii=False,
                        allow_nan=False,
                    )
                os.replace(tmp_path, file_path)
            return True
        except Exception as e:
            logger.warning(
                "[MemoryService] Error saving profile (%s)",
                type(e).__name__,
            )
            return False
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError as cleanup_error:
                    logger.warning('[MemoryService] Failed to remove profile temp file')

    def add_to_watchlist(
        self,
        user_id: str,
        ticker: str,
        *,
        name: Optional[str] = None,
        tags: Optional[List[str]] = None,
        note: Optional[str] = None,
        group: Optional[str] = None,
        priority: Optional[int] = None,
        watch_reason: Optional[str] = None,
        research_status: Optional[str] = None,
        max_watchlist: Optional[int] = None,
    ) -> bool:
        """添加关注。可选 name/tags/note/group/priority/watch_reason 元信息会写入 watchlist_meta。"""
        clean_ticker = str(ticker or "").strip().upper()
        if not clean_ticker:
            return False
        with _PROFILE_LOCK:
            profile = self.get_user_profile(user_id)
            if clean_ticker not in profile.watchlist:
                if max_watchlist is not None and max_watchlist >= 0 and len(profile.watchlist) >= max_watchlist:
                    raise WatchlistLimitExceeded(
                        limit=max_watchlist,
                        current=len(profile.watchlist),
                    )
                profile.watchlist.append(clean_ticker)
            # merge metadata (None values do not overwrite existing fields)
            existing = profile.watchlist_meta.get(clean_ticker, {}) if isinstance(profile.watchlist_meta, dict) else {}
            merged = dict(existing)
            if name is not None:
                merged["name"] = str(name).strip()
            if tags is not None:
                merged["tags"] = [str(t).strip() for t in tags if str(t).strip()]
            if note is not None:
                merged["note"] = str(note)
            if group is not None:
                merged["group"] = str(group).strip()
            if priority is not None:
                merged["priority"] = safe_int(priority, 0) or 0
            if watch_reason is not None:
                merged["watch_reason"] = str(watch_reason).strip()
            if research_status is not None:
                merged["research_status"] = str(research_status).strip()
            if "added_at" not in merged:
                merged["added_at"] = datetime.now().isoformat()
            merged["updated_at"] = datetime.now().isoformat()
            profile.watchlist_meta[clean_ticker] = merged
            return self.update_user_profile(profile)

    def update_watchlist_meta(
        self,
        user_id: str,
        ticker: str,
        *,
        name: Optional[str] = None,
        tags: Optional[List[str]] = None,
        note: Optional[str] = None,
        group: Optional[str] = None,
        priority: Optional[int] = None,
        watch_reason: Optional[str] = None,
        research_status: Optional[str] = None,
    ) -> bool:
        """更新一个已存在的 watchlist 条目的元信息。ticker 必须已在列表中。"""
        clean_ticker = str(ticker or "").strip().upper()
        with _PROFILE_LOCK:
            profile = self.get_user_profile(user_id)
            if clean_ticker not in profile.watchlist:
                return False
            return self.add_to_watchlist(
                user_id,
                clean_ticker,
                name=name,
                tags=tags,
                note=note,
                group=group,
                priority=priority,
                watch_reason=watch_reason,
                research_status=research_status,
            )

    def remove_from_watchlist(self, user_id: str, ticker: str) -> bool:
        """取消关注"""
        clean_ticker = str(ticker or "").strip().upper()
        with _PROFILE_LOCK:
            profile = self.get_user_profile(user_id)
            # 同时清理 ticker(原样) 与 标准化形式,避免遗留旧数据
            removed = False
            for variant in {ticker, clean_ticker}:
                if variant in profile.watchlist:
                    profile.watchlist.remove(variant)
                    removed = True
            if isinstance(profile.watchlist_meta, dict):
                profile.watchlist_meta.pop(clean_ticker, None)
                profile.watchlist_meta.pop(ticker, None)
            if removed:
                return self.update_user_profile(profile)
            return True

    def list_watchlist_items(self, user_id: str) -> List[Dict[str, Any]]:
        """返回 watchlist 数组,每项包含 ticker + meta。前端管理页用。"""
        profile = self.get_user_profile(user_id)
        meta = profile.watchlist_meta if isinstance(profile.watchlist_meta, dict) else {}
        items: List[Dict[str, Any]] = []
        for ticker in profile.watchlist:
            ticker_key = str(ticker).strip()
            entry = meta.get(ticker_key, {})
            if not entry and ticker_key.upper() != ticker_key:
                entry = meta.get(ticker_key.upper(), {})
            items.append({
                "ticker": ticker_key,
                "name": entry.get("name"),
                "tags": entry.get("tags") or [],
                "note": entry.get("note"),
                "group": entry.get("group"),
                "priority": entry.get("priority"),
                "watch_reason": entry.get("watch_reason"),
                "research_status": entry.get("research_status") or "new",
                "added_at": entry.get("added_at"),
                "updated_at": entry.get("updated_at"),
            })
        return items

    def set_preference(self, user_id: str, key: str, value: Any) -> bool:
        """设置偏好"""
        with _PROFILE_LOCK:
            profile = self.get_user_profile(user_id)
            profile.preferences[key] = value
            return self.update_user_profile(profile)
