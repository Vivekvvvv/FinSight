# -*- coding: utf-8 -*-
"""上下文链的词边界匹配 helper。

``context.py`` 各匹配点此前手写三套边界正则（R29/R30/R33/R34/R-类 系列
修复留痕）：大写 ticker token 版、小写 ASCII 词版、CJK 子串版。本模块
把三套语义收成显式命名函数，正则只写一次；其余匹配点统一走这里。

边界语义与既有修复逐点对齐，**勿擅自"优化"差异**：

- ``contains_symbol``：左界排除 ``[A-Z0-9.]``（".HK" 式前缀与 "BAAPL"
  粘连都不算），右界只排除 ``[A-Z0-9]``（允许 "AAPL.HK" 后缀形态）—
  用于 ticker/symbol/market-tag 三类；
- ``contains_ascii_word``：左右界都排除 ``[a-z0-9]``——用于 ASCII
  公司名与市场 hint 关键词；
- ``contains_suffix_code``：右界排除 ``[a-z0-9]``、左界允许紧贴代码
  ——".l"/".t" 类代码后缀专用（"vod.l"→UK 命中，".t"⊄".txt"）；
- ``contains_name``：按书写系统分流——CJK 名子串命中（中文名天然嵌在
  长句里），ASCII 名转 ``contains_ascii_word``。
"""

from __future__ import annotations

import re

_CJK_RE = re.compile(r"[一-鿿]")


def has_cjk(text: str) -> bool:
    """文本是否含 CJK 字符（决定走子串还是词界口径）。"""
    return bool(text) and _CJK_RE.search(text) is not None


def contains_symbol(text: str, symbol: str) -> bool:
    """ticker/tag 以独立 token 出现才命中（大小写不敏感）。

    ``"T"⊄"THE"``、``"AI"⊄"SAID"``、``"US"⊄"AUSTRALIAN"``；``"AAPL.HK"``
    里 ``"AAPL"`` 命中（右侧 '.' 允许）。左界额外排除 '.'——``"X.AAPL"``
    里的 ``"AAPL"`` 不命中。
    """
    if not text or not symbol:
        return False
    return bool(
        re.search(
            rf"(?<![A-Z0-9.]){re.escape(symbol.upper())}(?![A-Z0-9])",
            text.upper(),
        )
    )


def contains_ascii_word(text: str, word: str) -> bool:
    """ASCII 词独立成词才命中（大小写不敏感）。

    ``"apple"⊄"applepie"``、``"us"⊄"discuss"``、``"adr"⊄"adrian"``；
    "apple pie"/"dell laptop" 词组仍命中——词界只能挡粘连，分不清词组
    内的普通名词，需词表/上下文辅助（context.py 已记录的已知边界）。
    """
    if not text or not word:
        return False
    return bool(
        re.search(
            r"(?<![a-z0-9])" + re.escape(word.lower()) + r"(?![a-z0-9])",
            text.lower(),
        )
    )


def contains_suffix_code(text: str, code: str) -> bool:
    """``.l``/``.t`` 类代码后缀命中判定（大小写不敏感）。

    左界允许紧贴代码（``"vod.l"`` → UK）；右界排除 ``[a-z0-9]``——
    ``".t"⊄".txt"`` 不误判 JP。
    """
    if not text or not code:
        return False
    return bool(re.search(re.escape(code.lower()) + r"(?![a-z0-9])", text.lower()))


def contains_name(query: str, name: str) -> bool:
    """公司名该不该在 query 里命中：CJK 名走子串，ASCII 名要求词界。

    裸 ``name.lower() in query.lower()`` 让 ``"Apple"⊂"applepie"``、
    ``"Dell"⊂"delllaptop"`` 被当成显式公司名提及；CJK 名（"苹果"/"茅台"）
    在中英混排里永远以子串出现，不能套 ASCII 词界。
    """
    if not query or not name:
        return False
    if has_cjk(name):
        return name.lower() in query.lower()
    return contains_ascii_word(query, name)


__all__ = [
    "has_cjk",
    "contains_symbol",
    "contains_ascii_word",
    "contains_suffix_code",
    "contains_name",
]
