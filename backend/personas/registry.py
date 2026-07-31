# -*- coding: utf-8 -*-
"""
Persona Registry — Investment-style 视角注入系统

将"投资风格"建模为可插拔的配置单元，每个 Persona 包含三要素：
  1. agent_weights      —— 调整 policy_gate 中各 Agent 的选择评分
  2. synthesis_lens     —— 注入 synthesize 节点的视角 prompt 片段
  3. report_sections_priority —— 报告章节优先级覆盖

YAML 配置位于 backend/personas/*.yaml，启动时自动加载。

设计原则：
- **软调权而非硬切换**：weights 倾斜但不阉割（下限 0.2），保留数据完整性。
- **诚实优先级 > 风格一致性**：lens prompt 中明确要求模型在数据矛盾时如实指出。
- **向下兼容**：persona_id=None 或缺失时，行为与现版本完全一致（neutral 默认）。
"""

from __future__ import annotations

import logging
import math
import threading
from pathlib import Path
from typing import Dict, List, Literal, Optional

import yaml
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

PERSONA_DIR = Path(__file__).parent

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class AgentWeights(BaseModel):
    """Per-agent selection-score multiplier.

    Applied in policy_gate after the base capability score is computed.
    Lower-bounded at 0.2 to prevent total agent suppression.
    """

    fundamental: float = 1.0
    macro: float = 1.0
    risk: float = 1.0
    price: float = 1.0
    technical: float = 1.0
    news: float = 1.0
    deep_search: float = 1.0

    model_config = {"extra": "ignore"}

    @field_validator(
        "fundamental", "macro", "risk", "price", "technical", "news", "deep_search",
        mode="after",
    )
    @classmethod
    def _clamp(cls, v: float) -> float:
        # Hard lower bound 0.2 → prevents total suppression of any agent
        # Upper bound 3.0 → prevents pathological domination
        if v is None:
            return 1.0
        value = float(v)
        if not math.isfinite(value):
            return 1.0
        return max(0.2, min(3.0, value))

    def get(self, agent_name: str, default: float = 1.0) -> float:
        """Look up weight by agent_name (with or without `_agent` suffix)."""
        key = (agent_name or "").lower().removesuffix("_agent")
        # Use class-level model_fields (Pydantic v2.11+ deprecates instance access).
        return getattr(self, key, default) if key in type(self).model_fields else default


class Persona(BaseModel):
    id: str = Field(..., description="unique persona identifier")
    display_name_zh: str
    display_name_en: str
    emoji: str = "🧊"
    philosophy: str = ""
    agent_weights: AgentWeights = Field(default_factory=AgentWeights)
    synthesis_lens: str = ""
    report_sections_priority: List[str] = Field(default_factory=list)
    risk_tolerance: Literal["low", "medium", "high"] = "medium"

    model_config = {"extra": "ignore"}


# ---------------------------------------------------------------------------
# Registry (process-wide singleton, lazy-loaded, thread-safe)
# ---------------------------------------------------------------------------

_REGISTRY: Dict[str, Persona] = {}
_LOCK = threading.Lock()
_LOADED = False

_DEFAULT_NEUTRAL = Persona(
    id="neutral",
    display_name_zh="中立分析师",
    display_name_en="Neutral Analyst",
    emoji="🧊",
    philosophy="数据驱动、不偏不倚（兜底默认）",
    synthesis_lens="",
    report_sections_priority=[],
)


def _load_yaml_file(path: Path) -> Optional[Persona]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            logger.warning("[personas] %s does not contain a mapping; skipped", path.name)
            return None
        return Persona(**raw)
    except Exception as exc:
        logger.warning("[personas] failed to parse %s: %s", path.name, type(exc).__name__)
        return None


def _load_all_unsafe() -> Dict[str, Persona]:
    registry: Dict[str, Persona] = {}
    if not PERSONA_DIR.exists():
        return registry
    for yaml_path in sorted(PERSONA_DIR.glob("*.yaml")):
        persona = _load_yaml_file(yaml_path)
        if persona is None:
            continue
        if persona.id in registry:
            logger.warning("[personas] duplicate id '%s' in %s; overriding", persona.id, yaml_path.name)
        registry[persona.id] = persona
    # Always ensure neutral fallback exists
    registry.setdefault("neutral", _DEFAULT_NEUTRAL)
    return registry


def load_personas(*, force_reload: bool = False) -> Dict[str, Persona]:
    """Load (or return cached) all personas. Thread-safe."""
    global _LOADED
    if _LOADED and not force_reload:
        return _REGISTRY
    with _LOCK:
        if _LOADED and not force_reload:
            return _REGISTRY
        _REGISTRY.clear()
        _REGISTRY.update(_load_all_unsafe())
        _LOADED = True
    return _REGISTRY


def get_persona(persona_id: Optional[str]) -> Persona:
    """Resolve persona by id, falling back to neutral on miss/None."""
    registry = load_personas()
    if not persona_id:
        return registry.get("neutral", _DEFAULT_NEUTRAL)
    return registry.get(str(persona_id).strip(), registry.get("neutral", _DEFAULT_NEUTRAL))


def list_personas() -> List[Persona]:
    """Return all personas in deterministic order (neutral first)."""
    registry = load_personas()
    items = list(registry.values())
    items.sort(key=lambda p: (0 if p.id == "neutral" else 1, p.id))
    return items


__all__ = [
    "Persona",
    "AgentWeights",
    "get_persona",
    "list_personas",
    "load_personas",
]
