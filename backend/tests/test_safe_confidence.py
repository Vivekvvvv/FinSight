# -*- coding: utf-8 -*-
"""R65 回归：_safe_confidence 兑现 docstring，映射 high/medium/low 字符串。

旧实现只 float(value)，"high"/"medium"/"low" 都抛 ValueError 塌成 0.7 默认，
信号丢失（high 与 low 无法区分）。补 label 映射；数字/None/非法路径不变。
"""
from __future__ import annotations

import pytest

from backend.graph.report_builder import _safe_confidence, _to_json_compatible


def test_string_labels_mapped():
    assert _safe_confidence("high") == 0.9
    assert _safe_confidence("medium") == 0.6
    assert _safe_confidence("low") == 0.3
    # 大小写 / 空白不敏感
    assert _safe_confidence("  HIGH ") == 0.9
    assert _safe_confidence("Low") == 0.3


def test_numeric_paths_unchanged():
    assert _safe_confidence(0.85) == 0.85
    assert _safe_confidence("0.75") == 0.75  # 数字字符串仍走 float
    assert _safe_confidence(1) == 1.0


def test_none_and_garbage_fall_back_to_default():
    assert _safe_confidence(None) == 0.7
    assert _safe_confidence("garbage") == 0.7
    assert _safe_confidence(None, default=0.5) == 0.5
    assert _safe_confidence([], default=0.4) == 0.4


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_confidence_falls_back_to_default(value):
    assert _safe_confidence(value) == 0.7
    assert _safe_confidence(value, default=0.4) == 0.4


def test_to_json_compatible_replaces_non_finite_numbers():
    result = _to_json_compatible(
        {"score": float("nan"), "values": [1.0, float("inf")]}
    )

    assert result == {"score": None, "values": [1.0, None]}
