# -*- coding: utf-8 -*-
"""Persona system — investment-style switching for FinSight pipeline."""

from backend.personas.registry import (
    AgentWeights,
    Persona,
    get_persona,
    list_personas,
    load_personas,
)

__all__ = [
    "AgentWeights",
    "Persona",
    "get_persona",
    "list_personas",
    "load_personas",
]
