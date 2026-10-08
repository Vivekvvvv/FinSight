# -*- coding: utf-8 -*-
"""外部数据源的"毒条目"归一化层。

上游（Finnhub/yfinance/AlphaVantage/Tavily/Exa/东财/腾讯等）返回的列表里
常混入非 dict 条目（str/None/list）或字段为 None 的"毒记录"；此前 20+ 个
tools 文件各自写 `isinstance(x, dict)` + `.get(...) or ...` 守卫，写法分散、
同型 bug 反复出现（see fix(search)/fix(news)/fix(price)/fix(tencent) 系列）。

本模块提供统一入口：
  - ``iter_dict_items``：过滤掉非 dict 条目，按条跳过而不是毁整批；
  - ``iter_attr_items``：对象型载荷（Exa 等）的缺属性守卫，同口径按条跳过；
  - ``text_or`` / ``num_or``：字段级归一化，把 present-None / 非 str 收敛到
    默认值，避免下游 `title.lower()`/`* 100` 之类的 TypeError/AttributeError。

只处理"上游数据格式不可信"这一层，不做业务过滤（来源可信度、URL 合法性
等仍由调用方负责）。
"""

from __future__ import annotations

from typing import Any, Iterable, Iterator, Optional


def iter_dict_items(items: Iterable[Any] | None) -> Iterator[dict]:
    """逐个产出 iterable 里的 dict 条目，非 dict 毒条目按条跳过。

    代替各 provider 循环里重复的 ``if not isinstance(x, dict): continue``。
    ``items`` 为 None 或不可迭代时产出空迭代，由调用方自行区分"空"与"坏"。
    """
    if not items:
        return
    for item in items:
        if isinstance(item, dict):
            yield item


def text_or(value: Any, default: str = "") -> str:
    """把上游字段归一化为 str：None/非 str/非数值收敛到 ``default``。

    present-None 字段（上游返回 ``{"title": null}``）和标量（int/float/bool）
    都安全；dict/list 等结构化值视为无效，返回 ``default``。
    """
    if value is None:
        return default
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    return default


def num_or(value: Any, default: float = 0.0) -> float:
    """把上游字段归一化为 float：非法/None/NaN/inf 收敛到 ``default``。

    present-None、非数值字符串、"N/A"、NaN、±inf 都视为无效。
    """
    if value is None or isinstance(value, bool):
        return default
    try:
        n = float(value)
    except (TypeError, ValueError):
        return default
    if n != n or n in (float("inf"), float("-inf")):  # NaN / ±inf
        return default
    return n


def iter_attr_items(items: Iterable[Any] | None, *required_attrs: str) -> Iterator[Any]:
    """逐个产出同时具备 ``required_attrs`` 的条目——Exa 等对象型载荷的守卫。

    等价于各循环里的 ``hasattr(x, 'title') and hasattr(x, 'url')`` 手工守卫，
    缺属性的毒条目按条跳过而不是毁整批。``items`` 为 None/空时产出空迭代。
    """
    if not items:
        return
    for item in items:
        if item is None:
            continue
        if all(hasattr(item, attr) for attr in required_attrs):
            yield item


def num_or_none(value: Any) -> Optional[float]:
    """同 ``num_or``，但非法值返回 ``None``——区分"0"与"无数据"。"""
    if value is None or isinstance(value, bool):
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n != n or n in (float("inf"), float("-inf")):
        return None
    return n


__all__ = ["iter_dict_items", "iter_attr_items", "text_or", "num_or", "num_or_none"]
