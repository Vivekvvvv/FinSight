# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import logging
from typing import Any

from backend.graph.state import GraphState
from backend.services.alert_scheduler import fetch_price_snapshot
from backend.services.entitlements import DEFAULT_PLAN, PLAN_LIMITS, get_entitlements_service
from backend.services.subscription_service import SubscriptionLimitExceeded, get_subscription_service
from backend.utils.quote import safe_float, safe_int

logger = logging.getLogger(__name__)


def _resolve_user_email(state: GraphState) -> str | None:
    direct = str(state.get("user_email") or "").strip()
    if direct:
        return direct
    ui_context = state.get("ui_context") or {}
    fallback = str((ui_context.get("user_email") if isinstance(ui_context, dict) else "") or "").strip()
    return fallback or None


def _resolve_max_alerts(state: GraphState) -> int:
    """只按入口提供的认证身份查询配额，缺少身份时按免费套餐处理。"""
    ui_context = state.get("ui_context") or {}
    identity = ui_context.get("_authenticated_user") if isinstance(ui_context, dict) else None
    if not isinstance(identity, dict):
        identity = {}
    user_id = str(identity.get("user_id") or "").strip()
    if not user_id:
        return PLAN_LIMITS[DEFAULT_PLAN]["max_alerts"]
    entitlements = get_entitlements_service().get_entitlements(
        user_id, role=str(identity.get("role") or "user"),
    )
    return safe_int((entitlements.get("limits") or {}).get("max_alerts"), 0) or 0


def _resolve_ticker(state: GraphState, alert_params: dict[str, Any]) -> str | None:
    ticker = str(alert_params.get("ticker") or "").strip().upper()
    if ticker:
        return ticker
    subject = state.get("subject") or {}
    tickers = subject.get("tickers") if isinstance(subject, dict) else None
    if isinstance(tickers, list) and tickers:
        first = str(tickers[0] or "").strip().upper()
        if first:
            return first
    return None


def _build_success_markdown(*, ticker: str, mode: str, direction: str | None, price_target: float | None, price_threshold: float | None, alert_types: list[str]) -> str:
    if mode == "price_target":
        arrow = "上涨到" if direction == "above" else "下跌到"
        return (
            f"已为 `{ticker}` 创建到价提醒：{arrow} `{price_target}` 时提醒。\n"
            f"- 订阅类型：{', '.join(alert_types)}\n"
            "- 说明：系统已保留你原有订阅类型，并追加价格提醒。"
        )

    return (
        f"已为 `{ticker}` 创建涨跌幅提醒：绝对涨跌幅达到 `{price_threshold}%` 时提醒。\n"
        f"- 订阅类型：{', '.join(alert_types)}\n"
        "- 说明：系统已保留你原有订阅类型，并追加价格提醒。"
    )


async def alert_action(state: GraphState) -> dict[str, Any]:
    user_email = _resolve_user_email(state)
    if not user_email:
        return {
            "alert_valid": False,
            "skip_session_context": True,
            "artifacts": {
                "draft_markdown": "请先在设置中配置提醒邮箱，然后再说「某股票涨到/跌到XX提醒我」。"
            },
        }

    alert_params = state.get("alert_params") or {}
    ticker = _resolve_ticker(state, alert_params)
    if not ticker:
        return {
            "alert_valid": False,
            "skip_session_context": True,
            "artifacts": {
                "draft_markdown": "我还不知道你要订阅哪只股票，请补充 ticker（例如 AAPL）。"
            },
        }

    mode = str(alert_params.get("alert_mode") or "price_change_pct")
    price_target = alert_params.get("price_target")
    price_threshold = alert_params.get("price_threshold")
    direction = alert_params.get("direction")

    if mode == "price_target":
        price_target = safe_float(price_target)
        if price_target is None or price_target <= 0:
            return {
                "alert_valid": False,
                "skip_session_context": True,
                "artifacts": {"draft_markdown": "到价提醒的目标价格必须是大于 0 的有效数字，请修正后重试。"},
            }
        if direction not in {"above", "below"}:
            # 多源外网抓取，须卸载线程池，协程体内直接调会阻塞事件循环
            try:
                snap = await asyncio.to_thread(fetch_price_snapshot, ticker)
            except Exception:
                logger.warning("Alert direction quote unavailable")
                snap = None
            current_price = safe_float(snap.price if snap is not None else None)
            if (
                current_price is None or current_price <= 0
                or str(getattr(snap, "ticker", "") or "").strip().upper() != ticker
            ):
                return {
                    "alert_valid": False,
                    "skip_session_context": True,
                    "artifacts": {"draft_markdown": "暂时无法获取有效行情来判断提醒方向，请明确说「涨到」或「跌到」目标价，或稍后重试。"},
                }
            direction = "above" if price_target >= current_price else "below"
    else:
        price_threshold = safe_float(price_threshold)
        if price_threshold is None or price_threshold <= 0:
            return {
                "alert_valid": False,
                "skip_session_context": True,
                "artifacts": {"draft_markdown": "涨跌幅提醒的阈值必须是大于 0 的有效数字，请修正后重试。"},
            }

    svc = get_subscription_service()
    max_alerts = await asyncio.to_thread(_resolve_max_alerts, state)
    try:
        ok = await asyncio.to_thread(
            svc.subscribe,
            email=user_email,
            ticker=ticker,
            alert_types=["price_change"],
            price_threshold=price_threshold,
            alert_mode=mode,
            price_target=price_target,
            direction=direction,
            max_subscriptions=max_alerts,
            preserve_existing_alerts=True,
        )
    except SubscriptionLimitExceeded as exc:
        return {
            "alert_valid": False,
            "skip_session_context": True,
            "artifacts": {
                "draft_markdown": (
                    f"提醒数量已达到当前套餐上限（{exc.current}/{exc.limit}）。\n"
                    "请删除不需要的提醒或升级套餐后再创建；已有提醒仍可更新。"
                )
            },
        }

    if not ok:
        return {
            "alert_valid": False,
            "skip_session_context": True,
            "artifacts": {"draft_markdown": "提醒创建失败，请稍后重试。"},
        }

    subscriptions = await asyncio.to_thread(svc.get_subscriptions, user_email)
    saved = next(
        (item for item in subscriptions if str(item.get("ticker") or "").strip().upper() == ticker),
        {},
    )
    merged_alert_types = saved.get("alert_types") or ["price_change"]
    markdown = _build_success_markdown(
        ticker=ticker,
        mode=mode,
        direction=direction,
        price_target=price_target,
        price_threshold=price_threshold,
        alert_types=merged_alert_types,
    )

    return {
        "alert_valid": True,
        "skip_session_context": True,
        "artifacts": {"draft_markdown": markdown},
    }


__all__ = ["alert_action"]
