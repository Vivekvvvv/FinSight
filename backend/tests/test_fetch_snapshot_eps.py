# -*- coding: utf-8 -*-
"""R75：fetch_snapshot 的 eps 用 `info.get("trailingEps") or info.get("forwardEps")` ——
trailingEps=0.0（盈亏平衡，真实值）是 falsy，被 forwardEps（分析师预测值）
静默顶替：快照把预测当成实际 EPS 展示，语义完全不同。改显式 None 判断——
trailing 缺失才回退 forward，0.0/负值如实保留。"""
from __future__ import annotations

import yfinance

from backend.dashboard import data_fetchers


class _FakeTicker:
    def __init__(self, info):
        self.info = info

    def history(self, **_kw):
        raise RuntimeError("no history in tests")


def _patch(monkeypatch, info):
    monkeypatch.setattr(yfinance, "Ticker", lambda _s: _FakeTicker(info))


def test_trailing_eps_zero_kept(monkeypatch):
    """trailingEps=0.0 是真实值，不该被 forwardEps 顶替——修前得 1.5。"""
    _patch(monkeypatch, {"trailingEps": 0.0, "forwardEps": 1.5})
    out = data_fetchers.fetch_snapshot("ZERO", "equity")
    assert out is not None
    assert out["eps"] == 0.0


def test_trailing_eps_none_falls_back_to_forward(monkeypatch):
    """trailingEps=None（缺失）才回退 forwardEps——兜底语义保留。"""
    _patch(monkeypatch, {"trailingEps": None, "forwardEps": 1.5})
    out = data_fetchers.fetch_snapshot("MISS", "equity")
    assert out is not None
    assert out["eps"] == 1.5


def test_trailing_eps_key_absent_falls_back(monkeypatch):
    """trailingEps 键不存在同样回退 forwardEps。"""
    _patch(monkeypatch, {"forwardEps": 2.25})
    out = data_fetchers.fetch_snapshot("ABS", "equity")
    assert out is not None
    assert out["eps"] == 2.25


def test_negative_trailing_eps_kept(monkeypatch):
    """负 EPS（亏损）如实保留——回归保护。"""
    _patch(monkeypatch, {"trailingEps": -0.5, "forwardEps": 1.5})
    out = data_fetchers.fetch_snapshot("LOSS", "equity")
    assert out is not None
    assert out["eps"] == -0.5


def test_both_missing_gives_none(monkeypatch):
    """两者皆无 → eps=None（而不是虚构 0）——不吞数据。"""
    _patch(monkeypatch, {"trailingEps": None, "forwardEps": None})
    out = data_fetchers.fetch_snapshot("NONE", "equity")
    assert out is not None
    assert out["eps"] is None
