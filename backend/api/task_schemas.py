# -*- coding: utf-8 -*-
"""Task API response schemas."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class AITaskResponse(BaseModel):
    """Wire-format for a single AI task card."""

    id: str
    title: str
    category: str
    priority: int = Field(default=3, ge=1, le=5)
    reason: str = ""
    icon: str = "activity"
    execution_params: dict | None = None
    source: Literal["rule", "llm"] = "rule"

    @field_validator("priority", mode="before")
    @classmethod
    def reject_boolean_priority(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("task priority must not be boolean")
        return value


__all__ = ["AITaskResponse"]
