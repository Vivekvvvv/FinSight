"""Pydantic 数值字段的 bool 防御。

Python 里 `bool` 是 `int` 的子类，Pydantic 非 strict 模式会把 `True` 悄悄
收成 `1`。对于 LLM 工具调用这类外部输入，`limit=True` 应当直接被拒绝，而不是
变成 `limit=1` 继续跑下去。

用法：让模型继承 `RejectBooleanNumbers`，它声明的所有 int/float 字段（含
`Optional[...]`）都会自动拒绝布尔值，新增字段无需再补校验器。
"""

from __future__ import annotations

import types
import typing
from typing import Any

from pydantic import BaseModel, model_validator

_NUMERIC_TYPES = (int, float)

# 每个模型类的数值字段（含别名）只解析一次
_numeric_key_cache: dict[type, frozenset[str]] = {}


def _unwrap(annotation: Any) -> list[Any]:
    """剥掉 Optional/Union/Annotated，返回候选类型列表。"""
    origin = typing.get_origin(annotation)

    if origin is typing.Union or origin is types.UnionType:
        candidates: list[Any] = []
        for arg in typing.get_args(annotation):
            if arg is type(None):
                continue
            candidates.extend(_unwrap(arg))
        return candidates

    if hasattr(annotation, "__metadata__"):  # typing.Annotated[...]
        args = typing.get_args(annotation)
        return _unwrap(args[0]) if args else []

    return [annotation]


def is_numeric_annotation(annotation: Any) -> bool:
    """注解是否为（可选的）int/float。`bool` 本身不算数值。"""
    for candidate in _unwrap(annotation):
        if candidate is bool:
            continue
        if isinstance(candidate, type) and issubclass(candidate, _NUMERIC_TYPES):
            return True
    return False


def numeric_input_keys(model: type[BaseModel]) -> frozenset[str]:
    """模型里数值字段可能出现的入参 key（字段名 + 别名）。"""
    cached = _numeric_key_cache.get(model)
    if cached is not None:
        return cached

    keys: set[str] = set()
    for name, field in model.model_fields.items():
        if not is_numeric_annotation(field.annotation):
            continue
        keys.add(name)
        for alias in (field.alias, field.validation_alias):
            if isinstance(alias, str):
                keys.add(alias)

    resolved = frozenset(keys)
    _numeric_key_cache[model] = resolved
    return resolved


class RejectBooleanNumbers(BaseModel):
    """数值字段收到 bool 时直接报错，而不是让 Pydantic 收成 0/1。"""

    @model_validator(mode="before")
    @classmethod
    def _reject_boolean_numeric_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        for key in numeric_input_keys(cls):
            if key in data and isinstance(data[key], bool):
                raise ValueError(f"{key} must not be boolean")
        return data
