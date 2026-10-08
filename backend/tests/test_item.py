# -*- coding: utf-8 -*-
"""tools/_item.py 归一化层测试——毒条目按条跳过、present-None/畸形字段收敛默认值。"""
from __future__ import annotations

from backend.tools._item import iter_dict_items, num_or, num_or_none, text_or


def test_iter_dict_items_skips_poison_entries():
    """上游列表混入 str/None/list/int 毒条目时按条跳过，不毁整批——
    同 fix(search)/fix(news) 系列里 isinstance(x, dict) 守卫的缺陷类。"""
    raw = [
        {"title": "ok"},
        "poison-string",
        None,
        ["nested", "list"],
        42,
        {"title": "ok2"},
    ]
    assert list(iter_dict_items(raw)) == [{"title": "ok"}, {"title": "ok2"}]


def test_iter_dict_items_empty_and_none():
    """None/空列表产出空迭代，由调用方区分'空'与'坏'。"""
    assert list(iter_dict_items(None)) == []
    assert list(iter_dict_items([])) == []


def test_text_or_normalizes_present_none_and_scalars():
    """present-None 字段（上游 {"title": null}）与非 str 标量都安全归一。"""
    assert text_or(None) == ""
    assert text_or(None, "fb") == "fb"
    assert text_or("keep") == "keep"
    assert text_or(42) == "42"
    assert text_or(1.5) == "1.5"
    assert text_or(True) == "True"
    # dict/list 结构化值视为无效
    assert text_or({"x": 1}) == ""
    assert text_or(["a"], "d") == "d"


def test_num_or_coerces_valid_and_falls_back():
    """None/bool/'N/A'/NaN/inf 收敛默认值；数字字符串正常转换。"""
    assert num_or(None) == 0.0
    assert num_or(None, 9.9) == 9.9
    assert num_or("N/A") == 0.0
    assert num_or("not a number") == 0.0
    assert num_or("1699999999") == 1699999999.0  # 字符串 epoch 仍可用
    assert num_or(3.14) == 3.14
    assert num_or(True) == 0.0          # bool 不算数值
    assert num_or(float("nan")) == 0.0
    assert num_or(float("inf")) == 0.0
    assert num_or({"x": 1}) == 0.0


def test_num_or_none_distinguishes_missing_from_zero():
    """同 num_or 但非法值返回 None——price 类字段需区分'0'与'无数据'。"""
    assert num_or_none(0) == 0.0        # 真实 0 保留
    assert num_or_none(None) is None
    assert num_or_none("N/A") is None
    assert num_or_none(float("nan")) is None
    assert num_or_none("2.5") == 2.5
    assert num_or_none(False) is None
