from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from backend.demo_mode import is_demo_mode


MARKET_KEYS = ("FMP_API_KEY", "ALPHA_VANTAGE_API_KEY", "FINNHUB_API_KEY", "TWELVE_DATA_API_KEY", "EODHD_API_KEY")


def _has_env(name: str) -> bool:
    return bool(str(os.getenv(name, "")).strip())


def _component(key: str, label: str, status: str, detail: str, required_action: str | None = None) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "status": status,
        "detail": detail,
        "required_action": required_action,
    }


def get_data_source_status() -> dict[str, Any]:
    demo_mode = is_demo_mode()
    has_paid_market_key = any(_has_env(name) for name in MARKET_KEYS)
    has_llm_key = _has_env("OPENAI_COMPATIBLE_API_KEY")
    has_auth_keys = _has_env("JWT_SECRET") and _has_env("API_AUTH_KEYS")

    components = [
        _component(
            "market_us",
            "美股行情",
            "demo" if demo_mode else ("live_ready" if has_paid_market_key else "fallback_ready"),
            "Demo Mode 使用内置差异化行情。" if demo_mode else (
                "检测到付费行情 key，优先使用真实外部源。"
                if has_paid_market_key
                else "未配置付费行情 key，使用 yfinance 免费兜底；失败时回落到 Demo。"
            ),
            None if demo_mode or has_paid_market_key else "可选配置 FMP_API_KEY 提升覆盖率。",
        ),
        _component(
            "market_cn",
            "A 股行情",
            "demo" if demo_mode else "fallback_ready",
            "Demo Mode 使用内置 A 股示例。" if demo_mode else "使用 BaoStock 免费兜底；失败时回落到 Demo。",
            None,
        ),
        _component(
            "market_hk",
            "港股行情",
            "demo" if demo_mode else "fallback_ready",
            "Demo Mode 使用内置港股示例。" if demo_mode else "使用 yfinance 单标的免费兜底；覆盖不足时回落到 Demo。",
            None,
        ),
        _component(
            "llm",
            "AI 研究生成",
            "demo" if demo_mode else ("live_ready" if has_llm_key else "missing_key"),
            "Demo Mode 可展示模板化研究输出。" if demo_mode else (
                "检测到 LLM key，可发起真实研究生成。"
                if has_llm_key
                else "未检测到 LLM key，Chat/深度研究会降级或不可用。"
            ),
            None if demo_mode or has_llm_key else "配置 OPENAI_COMPATIBLE_API_KEY。",
        ),
        _component(
            "rag",
            "本地证据检索",
            "fallback_ready",
            "可使用 hash fallback 验证链路；语义向量质量取决于本地模型与索引初始化。",
            "生产语义检索建议预热 BGE-M3 或兼容 embedding 服务。",
        ),
        _component(
            "auth",
            "访问控制",
            "demo" if demo_mode else ("live_ready" if has_auth_keys else "missing_key"),
            "Demo Mode 使用本地开发身份。" if demo_mode else (
                "JWT 与 API key 已配置。"
                if has_auth_keys
                else "JWT_SECRET 或 API_AUTH_KEYS 未完整配置。"
            ),
            None if demo_mode or has_auth_keys else "配置 JWT_SECRET 和 API_AUTH_KEYS。",
        ),
    ]

    missing_services = [
        name for name in ("JWT_SECRET", "API_AUTH_KEYS", "OPENAI_COMPATIBLE_API_KEY")
        if not _has_env(name)
    ]
    overall_status = "demo" if demo_mode else (
        "live_ready" if not missing_services else (
            "fallback_ready" if all(c["status"] in {"live_ready", "fallback_ready"} for c in components[:3]) else "needs_config"
        )
    )

    return {
        "success": True,
        "demo_mode": demo_mode,
        "data_source": "demo" if demo_mode else "live_or_local",
        "overall_status": overall_status,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "missing_services": missing_services,
        "components": components,
        "notes": [
            "所有行情、K 线和财务数据都应携带 evidence，说明 source/as_of/freshness/fallback。",
            "未配置真实 key 时，系统优先使用免费源；免费源失败才回落到明确标注的 Demo 数据。",
        ],
    }
