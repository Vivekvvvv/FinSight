# -*- coding: utf-8 -*-
"""extract_tickers：带标点 ticker 的提取缺陷。

bug A（幻影 ticker）：纯字母正则 `(?<![A-Za-z0-9.])([A-Za-z]{2,5})(?![A-Za-z0-9])`
的 lookbehind 不含 ``^``、lookahead 不含 ``.-`` —— ``^GSPC`` 里的 ``GSPC``、
``BRK.B`` 里的 ``BRK`` 被当成独立全大写 ticker 二次提取，产生幻影标的。

bug B（点号分级股被丢弃）：``BRK.B``/``BRK-B``/``ASML.AS`` 这类用户显式大写
输入的点号/连字符 ticker，被 dedicated dotted 正则捕获并通过了
is_probably_ticker，但验收分支只认 ``originally_upper``（纯字母匹配的集合），
结果被静默丢弃——只剩前缀 ``BRK`` 这个错误标的进入分析。
"""
from __future__ import annotations

from backend.config.ticker_mapping import extract_tickers


def _tickers(query: str) -> list[str]:
    meta = extract_tickers(query)
    return list(meta.get("tickers") or [])


def test_caret_index_does_not_emit_phantom_alpha_ticker():
    """`^GSPC` 只应提取出指数本身，不应多出一个 `GSPC` 幻影标的。"""
    tickers = _tickers("分析一下 ^GSPC 的走势")
    assert "^GSPC" in tickers
    assert "GSPC" not in tickers  # 修复前：['^GSPC', 'GSPC']


def test_dotted_class_share_not_dropped_to_prefix():
    """用户大写输入 `BRK.B` 应原样保留，不该降级成 `BRK`。"""
    tickers = _tickers("帮我看看 BRK.B 最近的估值")
    assert "BRK.B" in tickers
    assert "BRK" not in tickers  # 修复前：只有 ['BRK']——标的被换掉


def test_dashed_class_share_not_dropped_to_prefix():
    """yfinance 风格 `BRK-B` 同理。"""
    tickers = _tickers("BRK-B 和 AAPL 对比")
    assert "BRK-B" in tickers
    assert "AAPL" in tickers
    assert "BRK" not in tickers


def test_short_country_suffix_not_treated_as_ticker():
    """`U.S.`/`U.K.` 这类缩写仍是标点词，不能被放行成 ticker。"""
    assert "U.S" not in _tickers("U.S. market outlook")
    assert "U.K" not in _tickers("U.K economy")


def test_lowercase_dotted_still_rejected():
    """非全大写点号串照旧拒绝（保持原有 ALL-CAPS 门槛）。"""
    assert "e.g" not in _tickers("e.g. inflation data")


def test_existing_alpha_and_cn_paths_unchanged():
    """常规路径不回退：大写 ticker、公司别名、A股/港股代码。"""
    assert _tickers("看看 AAPL") == ["AAPL"]
    assert "AAPL" in _tickers("apple news today")
    assert "600519.SS" in _tickers("请分析 600519.SS 的估值")
    assert "0700.HK" in _tickers("看看 0700.HK")
