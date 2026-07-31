# -*- coding: utf-8 -*-
"""
Rebalance suggestion Pydantic schemas (Gate-6 + P3-6a).

Hard constraint HC-2: ``executable`` is always ``Literal[False]``,
``mode`` is always ``Literal["suggestion_only"]``.
"""
from __future__ import annotations

import json
import math
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ActionType(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    REDUCE = "reduce"
    INCREASE = "increase"


class RiskTier(str, Enum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class EvidenceSnapshot(BaseModel):
    """Immutable evidence captured at suggestion-generation time."""

    evidence_id: str
    source: str
    quote: str = Field(default="", max_length=200)
    report_id: str = ""
    captured_at: str = ""


class RebalanceConstraints(BaseModel):
    max_single_position_pct: float = Field(default=25.0, ge=1, le=100)
    max_turnover_pct: float = Field(default=30.0, ge=0, le=100)
    sector_concentration_limit: float = Field(default=40.0, ge=0, le=100)
    min_action_delta_pct: float = Field(default=1.0, ge=0, allow_inf_nan=False)


class RebalanceAction(BaseModel):
    ticker: str
    action: ActionType
    current_weight: float
    target_weight: float
    delta_weight: float
    reason: str = ""
    priority: int = Field(default=3, ge=1, le=5)
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_snapshots: list[EvidenceSnapshot] = Field(default_factory=list)


class ExpectedImpact(BaseModel):
    diversification_delta: str = ""
    risk_delta: str = ""
    estimated_turnover_pct: float = 0.0


class RebalanceSuggestion(BaseModel):
    suggestion_id: str
    mode: Literal["suggestion_only"] = "suggestion_only"
    executable: Literal[False] = False
    risk_tier: RiskTier = RiskTier.MODERATE
    constraints: RebalanceConstraints = Field(default_factory=RebalanceConstraints)
    summary: str = ""
    actions: list[RebalanceAction] = Field(default_factory=list)
    expected_impact: ExpectedImpact = Field(default_factory=ExpectedImpact)
    warnings: list[str] = Field(default_factory=list)
    disclaimer: str = "本建议仅供参考，不构成投资建议。请结合自身情况独立判断。"
    status: Literal["draft", "viewed", "dismissed", "sent_to_chat"] = "draft"
    created_at: str = ""
    degraded_mode: bool = False
    fallback_reason: str | None = None


class GenerateRebalanceRequest(BaseModel):
    session_id: str = Field(..., max_length=256)
    portfolio: list[dict] = Field(default_factory=list, max_length=200)
    risk_tier: RiskTier = RiskTier.MODERATE
    constraints: RebalanceConstraints = Field(default_factory=RebalanceConstraints)
    use_llm_enhancement: bool = False

    @field_validator("portfolio")
    @classmethod
    def validate_portfolio(cls, value: list[dict]) -> list[dict]:
        encoded = json.dumps(
            value, ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > 256 * 1024:
            raise ValueError("portfolio payload is too large")

        seen: set[str] = set()
        for item in value:
            ticker = item.get("ticker")
            if not isinstance(ticker, str):
                raise ValueError("portfolio ticker must be a string")
            ticker = ticker.strip().upper()
            if not ticker or len(ticker) > 32:
                raise ValueError("invalid portfolio ticker")
            if ticker in seen:
                raise ValueError("duplicate portfolio tickers are not allowed")
            seen.add(ticker)

            shares = item.get("shares", 0)
            if isinstance(shares, bool):
                raise ValueError("invalid portfolio shares")
            try:
                shares_value = float(shares)
            except (TypeError, ValueError) as exc:
                raise ValueError("invalid portfolio shares") from exc
            if not math.isfinite(shares_value) or shares_value < 0:
                raise ValueError("invalid portfolio shares")

            sector = item.get("sector")
            if sector is not None and (
                not isinstance(sector, str) or len(sector) > 128
            ):
                raise ValueError("invalid portfolio sector")
        return value


class PatchSuggestionRequest(BaseModel):
    status: Literal["viewed", "dismissed", "sent_to_chat"]
    # 可选属主声明：生产模式下强制用认证主体的 session 过滤；
    # dev 模式显式传入时也参与属主过滤（见 rebalance_router）。
    session_id: str = Field("", max_length=256)


__all__ = [
    "ActionType",
    "RiskTier",
    "EvidenceSnapshot",
    "RebalanceConstraints",
    "RebalanceAction",
    "ExpectedImpact",
    "RebalanceSuggestion",
    "GenerateRebalanceRequest",
    "PatchSuggestionRequest",
]
