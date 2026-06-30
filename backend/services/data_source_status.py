from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from backend.demo_mode import is_demo_mode


US_QUOTE_KEYS = ("ALPHA_VANTAGE_API_KEY", "FINNHUB_API_KEY", "TWELVE_DATA_API_KEY", "EODHD_API_KEY")


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
    has_us_quote_key = any(_has_env(name) for name in US_QUOTE_KEYS)
    has_fmp_key = _has_env("FMP_API_KEY")
    has_llm_key = _has_env("OPENAI_COMPATIBLE_API_KEY")
    has_auth_keys = _has_env("JWT_SECRET") and _has_env("API_AUTH_KEYS")

    components = [
        _component(
            "market_us",
            "美股行情",
            "demo" if demo_mode else ("live_ready" if has_us_quote_key else "fallback_ready"),
            "Demo Mode 使用内置行情。" if demo_mode else (
                "已检测到美股行情 key，单标的报价可优先使用真实外部源。"
                if has_us_quote_key
                else "未配置美股行情 key，单标的报价会尝试免费源；失败时回落到明确标注的候选数据。"
            ),
            None if demo_mode or has_us_quote_key else "可选配置 ALPHA_VANTAGE_API_KEY、FINNHUB_API_KEY、TWELVE_DATA_API_KEY 或 EODHD_API_KEY。",
        ),
        _component(
            "stock_screener",
            "股票筛选",
            "demo" if demo_mode else ("live_ready" if has_fmp_key else "fallback_ready"),
            "Demo Mode 使用内置候选池。" if demo_mode else (
                "已配置 FMP_API_KEY，股票发现可优先使用 FMP Stock Screener。"
                if has_fmp_key
                else "未配置 FMP_API_KEY，股票发现会使用明确标注的本地候选池，避免免费外部源超时导致空白。"
            ),
            None if demo_mode or has_fmp_key else "如需真实批量股票筛选，请配置 FMP_API_KEY。",
        ),
        _component(
            "market_cn",
            "A 股行情",
            "demo" if demo_mode else "fallback_ready",
            "Demo Mode 使用内置 A 股示例。" if demo_mode else "使用腾讯/东方财富/BaoStock 等免费源；失败时回落到明确标注的候选数据。",
            None,
        ),
        _component(
            "market_hk",
            "港股行情",
            "demo" if demo_mode else "fallback_ready",
            "Demo Mode 使用内置港股示例。" if demo_mode else "使用东方财富/yfinance 等免费源；覆盖不足时回落到明确标注的候选数据。",
            None,
        ),
        _component(
            "llm",
            "AI 研究生成",
            "demo" if demo_mode else ("live_ready" if has_llm_key else "missing_key"),
            "Demo Mode 可展示模板化研究输出。" if demo_mode else (
                "已检测到 LLM key，可发起真实研究生成。"
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
            "fallback_ready" if all(c["status"] in {"live_ready", "fallback_ready"} for c in components[:4]) else "needs_config"
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
            "行情、K 线、财务和筛选结果都应携带 evidence，说明 source/as_of/freshness/fallback。",
            "单标的行情 key 不等于批量筛选 key；FMP_API_KEY 专门用于股票发现里的真实批量筛选。",
            "未配置真实 key 时，系统优先使用免费源；免费源失败才回落到明确标注的 Demo/候选池数据。",
        ],
    }
