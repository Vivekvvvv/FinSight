# -*- coding: utf-8 -*-
"""User plan & feature entitlements service.

最小可用 Feature Gate / Plan 权限模型。
- Plans: free / pro / team / admin
- 存储: data/user_plans.json (JSON, 与 subscriptions/portfolio 风格一致)
- Admin role 自动映射到 admin plan, 无需配置
- 提供 quota 数值与 feature flag 两类判定

设计原则: KISS — 单文件存储 + 单例 service + 纯数据返回。不接 Stripe,
不做实时计量。前端拿 entitlements 后自行做提示/禁用即可。
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)
_PLANS_LOCK = threading.RLock()


def _reject_non_finite_json(value: str) -> None:
    raise ValueError(f"non-finite JSON value: {value}")

# ── 配置 ───────────────────────────────────────────────────────────

_DATA_DIR = Path(os.getenv("FINSIGHT_DATA_DIR", "data"))
PLANS_FILE = _DATA_DIR / "user_plans.json"

VALID_PLANS = ("free", "pro", "team", "admin")
DEFAULT_PLAN = "free"

# 每个 plan 的额度上限 (-1 表示无限)
# 这些数值是产品决策,后续可由 admin UI/Stripe webhook 改写
PLAN_LIMITS: Dict[str, Dict[str, int]] = {
    "free": {
        "max_watchlist": 5,
        "max_portfolio_positions": 5,
        "max_alerts": 3,
        "max_reports_per_day": 3,
        "max_deep_research_per_day": 0,
    },
    "pro": {
        "max_watchlist": 50,
        "max_portfolio_positions": 50,
        "max_alerts": 50,
        "max_reports_per_day": 30,
        "max_deep_research_per_day": 5,
    },
    "team": {
        "max_watchlist": 200,
        "max_portfolio_positions": 200,
        "max_alerts": 200,
        "max_reports_per_day": 200,
        "max_deep_research_per_day": 50,
    },
    "admin": {
        "max_watchlist": -1,
        "max_portfolio_positions": -1,
        "max_alerts": -1,
        "max_reports_per_day": -1,
        "max_deep_research_per_day": -1,
    },
}

# 功能开关 (true=plan 可访问,false=plan 被门控)
PLAN_FEATURES: Dict[str, Dict[str, bool]] = {
    "free": {
        "dashboard": True,
        "chat": True,
        "reports_library": True,
        "watchlist": True,
        "portfolio": True,
        "alerts": True,
        "deep_research": False,
        "backtest": False,
        "export_pdf": False,
        "rebalance": False,
        "cn_market": False,
        "rag_inspector": False,
    },
    "pro": {
        "dashboard": True,
        "chat": True,
        "reports_library": True,
        "watchlist": True,
        "portfolio": True,
        "alerts": True,
        "deep_research": True,
        "backtest": True,
        "export_pdf": True,
        "rebalance": True,
        "cn_market": True,
        "rag_inspector": False,
    },
    "team": {
        "dashboard": True,
        "chat": True,
        "reports_library": True,
        "watchlist": True,
        "portfolio": True,
        "alerts": True,
        "deep_research": True,
        "backtest": True,
        "export_pdf": True,
        "rebalance": True,
        "cn_market": True,
        "rag_inspector": False,
    },
    "admin": {
        "dashboard": True,
        "chat": True,
        "reports_library": True,
        "watchlist": True,
        "portfolio": True,
        "alerts": True,
        "deep_research": True,
        "backtest": True,
        "export_pdf": True,
        "rebalance": True,
        "cn_market": True,
        "rag_inspector": True,
    },
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_plan(value: Optional[str]) -> str:
    """规范化 plan 字符串, 非法值回退到 free。"""
    text = str(value or "").strip().lower()
    return text if text in VALID_PLANS else DEFAULT_PLAN


class EntitlementsService:
    """单例 service: 读取/写入 user_plans.json, 提供 entitlement 判定。"""

    def __init__(self) -> None:
        self._path = PLANS_FILE
        self._lock = _PLANS_LOCK
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._plans: Dict[str, Dict[str, Any]] = {}
        with self._lock:
            self._load()

    def _load(self) -> None:
        if not self._path.exists():
            self._plans = {}
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f, parse_constant=_reject_non_finite_json)
            if not isinstance(data, dict):
                raise ValueError("user plans payload must be a JSON object")
            if any(not isinstance(record, dict) for record in data.values()):
                raise ValueError("user plan entries must be JSON objects")
            self._plans = data
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            backup_path = self._path.with_name(
                f"{self._path.name}.{uuid4().hex}.corrupt"
            )
            os.replace(self._path, backup_path)
            logger.warning(
                "User plans file was corrupt and moved to a backup (%s)",
                type(exc).__name__,
            )
            self._plans = {}

    def _save(self) -> None:
        with self._lock:
            fd, tmp_path = tempfile.mkstemp(
                prefix=f"{self._path.name}.",
                suffix=".tmp",
                dir=str(self._path.parent),
                text=True,
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(
                        self._plans,
                        f,
                        indent=2,
                        ensure_ascii=False,
                        allow_nan=False,
                    )
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, self._path)
            finally:
                if os.path.exists(tmp_path):
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass

    # ── public API ────────────────────────────────────────────────

    def get_plan(self, user_id: str, *, role: str = "user") -> str:
        """返回用户当前 plan。admin role 始终返回 admin plan。"""
        if str(role or "").strip().lower() in {"admin", "internal"}:
            return "admin"
        record = self._plans.get(str(user_id or "").strip())
        if not isinstance(record, dict):
            return DEFAULT_PLAN
        return normalize_plan(record.get("plan"))

    def set_plan(self, user_id: str, plan: str, *, source: str = "manual") -> str:
        """更新用户 plan, 返回规范化后的 plan。"""
        normalized = normalize_plan(plan)
        uid = str(user_id or "").strip()
        if not uid:
            raise ValueError("user_id is required")
        with self._lock:
            self._load()
            self._plans[uid] = {
                "plan": normalized,
                "updated_at": _now_iso(),
                "source": str(source or "manual"),
            }
            self._save()
        return normalized

    def get_entitlements(self, user_id: str, *, role: str = "user") -> Dict[str, Any]:
        """返回完整 entitlement 对象 (plan + features + limits)。"""
        plan = self.get_plan(user_id, role=role)
        return {
            "user_id": str(user_id or "").strip(),
            "plan": plan,
            "role": str(role or "user").lower(),
            "features": dict(PLAN_FEATURES.get(plan, PLAN_FEATURES[DEFAULT_PLAN])),
            "limits": dict(PLAN_LIMITS.get(plan, PLAN_LIMITS[DEFAULT_PLAN])),
            "is_admin": plan == "admin",
        }

    def has_feature(self, user_id: str, feature: str, *, role: str = "user") -> bool:
        """单点查询某个 feature 是否启用。"""
        plan = self.get_plan(user_id, role=role)
        return bool(PLAN_FEATURES.get(plan, {}).get(feature, False))

    def check_quota(
        self,
        user_id: str,
        quota_key: str,
        current_count: int,
        *,
        role: str = "user",
    ) -> Dict[str, Any]:
        """检查配额。返回 {allowed, limit, current, remaining}。

        -1 视为无限,allowed 始终 True;否则当 current >= limit 时拒绝。
        """
        plan = self.get_plan(user_id, role=role)
        limit = int(PLAN_LIMITS.get(plan, {}).get(quota_key, 0))
        current = max(0, int(current_count))
        if limit < 0:
            return {"allowed": True, "limit": -1, "current": current, "remaining": -1, "plan": plan}
        remaining = max(0, limit - current)
        return {
            "allowed": current < limit,
            "limit": limit,
            "current": current,
            "remaining": remaining,
            "plan": plan,
        }

    # 测试 / admin 工具
    def reset_for_tests(self) -> None:
        with self._lock:
            self._plans = {}
            if self._path.exists():
                try:
                    self._path.unlink()
                except OSError:
                    pass


# ── 单例 ──────────────────────────────────────────────────────────

_service_instance: Optional[EntitlementsService] = None
_singleton_lock = threading.Lock()


def get_entitlements_service() -> EntitlementsService:
    global _service_instance
    if _service_instance is None:
        with _singleton_lock:
            if _service_instance is None:
                _service_instance = EntitlementsService()
    return _service_instance


def reset_entitlements_service_for_tests() -> None:
    """在测试中重置单例,以便指向新的临时文件。"""
    global _service_instance
    with _singleton_lock:
        _service_instance = None


# ── Usage view ────────────────────────────────────────────────────
#
# 把 "用户已用的数量" 集中到一个 helper, 避免每个 router 自己重新查表。
# 当前覆盖三类配额: max_reports_per_day / max_alerts / max_portfolio_positions。
# (max_watchlist 与 max_deep_research_per_day 暂未接 — 留 TODO)
#
# 设计原则: 单点失败不应让整个 entitlements 接口挂掉; 任意子查询异常时
# 该项 fallback 到 0, 调用方仍能看到 limit 而非 503。


def _today_utc_start_iso() -> str:
    """返回今天 UTC 0 点的 ISO 字符串, 作为 'today' 的下界。"""
    today = datetime.now(timezone.utc).date()
    return datetime(today.year, today.month, today.day, tzinfo=timezone.utc).isoformat()


def _build_session_id_for_user(user_id: str) -> str:
    return f"private:{str(user_id or '').strip()}:default"


def build_usage_view(
    user_id: str,
    *,
    email: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """计算用户当前各 quota 的 used 数; 返回 {quota_key: {used, limit, plan, remaining, allowed}}.

    需要外部数据源 (report_index / subscription_service / portfolio_store), 但都通过
    懒 import 取, 避免 entitlements 模块在 import 时拖出整个 web 栈。
    """
    service = get_entitlements_service()
    plan = service.get_plan(user_id)  # admin role 走另一条路径
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS[DEFAULT_PLAN])

    result: Dict[str, Dict[str, Any]] = {}

    # 1) max_reports_per_day
    reports_used = 0
    try:
        from backend.services.report_index import get_report_index_store

        store = get_report_index_store()
        reports_used = store.count_reports_since(
            session_id=_build_session_id_for_user(user_id),
            since=_today_utc_start_iso(),
        )
    except Exception as exc:
        logger.error(
            "build_usage_view: count_reports_since failed; fallback 0 (%s)",
            type(exc).__name__,
        )
        reports_used = 0
    result["max_reports_per_day"] = _quota_entry(
        plan=plan, used=reports_used, limit=int(limits.get("max_reports_per_day", 0))
    )

    # 2) max_alerts (基于订阅服务的当前订阅数)
    alerts_used = 0
    try:
        from backend.services.subscription_service import get_subscription_service

        sub_service = get_subscription_service()
        target_email = email if email else f"{user_id}@example.invalid"
        # 直接查 subscriptions[email]; 不存在则空列表
        subs = sub_service.get_subscriptions(email=target_email)
        alerts_used = len(subs)
    except Exception as exc:
        logger.error(
            "build_usage_view: count subscriptions failed; fallback 0 (%s)",
            type(exc).__name__,
        )
        alerts_used = 0
    result["max_alerts"] = _quota_entry(
        plan=plan, used=alerts_used, limit=int(limits.get("max_alerts", 0))
    )

    # 3) max_portfolio_positions
    pf_used = 0
    try:
        from backend.services.portfolio_store import get_positions

        positions = get_positions(_build_session_id_for_user(user_id))
        pf_used = len(positions) if positions else 0
    except Exception as exc:
        logger.error(
            "build_usage_view: count portfolio positions failed; fallback 0 (%s)",
            type(exc).__name__,
        )
        pf_used = 0
    result["max_portfolio_positions"] = _quota_entry(
        plan=plan, used=pf_used, limit=int(limits.get("max_portfolio_positions", 0))
    )

    # 4) 静态项: 其余配额返回 used=0 + limit (前端展示用)
    for quota_key in ("max_watchlist", "max_deep_research_per_day"):
        result[quota_key] = _quota_entry(
            plan=plan, used=0, limit=int(limits.get(quota_key, 0))
        )

    return result


def _quota_entry(*, plan: str, used: int, limit: int) -> Dict[str, Any]:
    """规范化一个 quota 条目 (used/limit/remaining/percent/allowed)."""
    used_clean = max(0, int(used))
    if limit < 0:
        return {
            "plan": plan,
            "used": used_clean,
            "limit": -1,
            "remaining": -1,
            "percent": 0,
            "allowed": True,
        }
    limit_clean = max(0, int(limit))
    remaining = max(0, limit_clean - used_clean)
    percent = int(round((used_clean / limit_clean) * 100)) if limit_clean > 0 else 100
    return {
        "plan": plan,
        "used": used_clean,
        "limit": limit_clean,
        "remaining": remaining,
        "percent": min(100, percent),
        "allowed": used_clean < limit_clean,
    }


# ── FastAPI 路由层强制函数 ────────────────────────────────────────
#
# 这些 helper 让任意 router 都可以用一行代码做 Plan 门控:
#   from backend.security.auth import get_current_user
#   from backend.services.entitlements import enforce_feature
#
#   @router.post("/some-pro-thing")
#   async def handler(current_user = Depends(get_current_user)):
#       enforce_feature(current_user, "deep_research")
#       ...
#
# 未登录用户 (principal=None) 视为 Free,被 enforce_feature 抛 401/403。

def enforce_feature(principal: Any, feature: str) -> None:
    """如果用户 plan 不含该 feature, 抛 HTTPException 403。

    principal 可能为 None (匿名) — 此时按 free plan 判定。
    """
    from fastapi import HTTPException

    user_id = ""
    role = "user"
    if principal is not None:
        user_id = str(getattr(principal, "user_id", "") or "")
        role = str(getattr(principal, "role", "user") or "user")
    service = get_entitlements_service()
    if not service.has_feature(user_id, feature, role=role):
        plan = service.get_plan(user_id, role=role)
        raise HTTPException(
            status_code=403,
            detail={
                "code": "plan_feature_required",
                "feature": feature,
                "plan": plan,
                "message": f"Your {plan} plan does not include '{feature}'. Upgrade to unlock.",
            },
        )


def enforce_quota(
    principal: Any,
    quota_key: str,
    current_count: int,
) -> Dict[str, Any]:
    """检查 quota; 超额抛 429。返回 entitlement decision (含 remaining 等)。"""
    from fastapi import HTTPException

    user_id = ""
    role = "user"
    if principal is not None:
        user_id = str(getattr(principal, "user_id", "") or "")
        role = str(getattr(principal, "role", "user") or "user")
    service = get_entitlements_service()
    decision = service.check_quota(user_id, quota_key, current_count, role=role)
    if not decision["allowed"]:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "plan_quota_exceeded",
                "quota": quota_key,
                "plan": decision["plan"],
                "limit": decision["limit"],
                "current": decision["current"],
                "message": (
                    f"Daily/total quota '{quota_key}' reached on {decision['plan']} plan "
                    f"({decision['current']}/{decision['limit']}). Upgrade to continue."
                ),
            },
        )
    return decision


__all__ = [
    "DEFAULT_PLAN",
    "PLAN_LIMITS",
    "PLAN_FEATURES",
    "VALID_PLANS",
    "EntitlementsService",
    "build_usage_view",
    "enforce_feature",
    "enforce_quota",
    "get_entitlements_service",
    "normalize_plan",
    "reset_entitlements_service_for_tests",
]
