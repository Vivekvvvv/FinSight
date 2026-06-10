# -*- coding: utf-8 -*-
"""
研究输出边界策略。

FinSight 是研究终端，不是投资顾问。本模块集中维护 AI 输出的
交易建议边界，避免各个 prompt 和降级分支各写一套规则。
"""

from __future__ import annotations

import re


RESEARCH_DISCLAIMER = "以上内容仅供研究复查，不构成投资建议。"

RESEARCH_STANCE_DEFAULT = "继续观察并复查证据"

TRADING_ACTION_PATTERN = re.compile(
    r"\b(BUY|SELL|HOLD|STRONG BUY|STRONG SELL)\b|"
    r"(建议|应该|可以|适合|考虑)?\s*(买入|卖出|持有|加仓|减仓|建仓|清仓|做多|做空)|"
    r"(止盈|止损|目标价|目标收益|收益承诺|仓位建议|入场|出场)",
    re.IGNORECASE,
)


def append_research_disclaimer(text: str) -> str:
    """确保输出带有统一研究免责声明。"""
    content = str(text or "").strip()
    if RESEARCH_DISCLAIMER in content:
        return content
    if not content:
        return RESEARCH_DISCLAIMER
    return f"{content}\n\n⚠️ {RESEARCH_DISCLAIMER}"


def sanitize_research_stance(value: object | None) -> str | None:
    """将兼容字段 recommendation 收口为研究立场，而不是交易动作。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if TRADING_ACTION_PATTERN.search(text):
        return RESEARCH_STANCE_DEFAULT
    return text


def research_boundary_prompt() -> str:
    """供 LLM prompt 复用的边界约束。"""
    return (
        "输出边界：只提供投资研究分析、风险复查和下一步核验动作；"
        "不得输出买入、卖出、持有、目标价、止盈止损、仓位比例、收益承诺或个性化交易决策；"
        f"末尾必须包含：{RESEARCH_DISCLAIMER}"
    )
