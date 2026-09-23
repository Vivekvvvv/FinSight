# -*- coding: utf-8 -*-
"""R31: _map_to_stooq_symbol 的加密货币排除必须是 token 级匹配，不是裸子串。

`crypto in upper` 让 "SOL"⊂"SOLV"(Solventum,NYSE)、"ETH"⊂"ETHO"
(Etho Climate ETF)、"BTC"⊂"BTCT"(BTC Digital,Nasdaq)、"ADA"⊂"ADAG"
(Adagene,Nasdaq) —— 合法美股被误判成加密货币，stooq 兜底源直接跳过。
"""
from __future__ import annotations

from backend.tools.price_history_providers import _map_to_stooq_symbol


def test_stock_tickers_containing_crypto_substrings_still_map():
    assert _map_to_stooq_symbol("SOLV") == "SOLV.us"   # SOL ⊂ SOLV
    assert _map_to_stooq_symbol("ETHO") == "ETHO.us"   # ETH ⊂ ETHO
    assert _map_to_stooq_symbol("BTCT") == "BTCT.us"   # BTC ⊂ BTCT
    assert _map_to_stooq_symbol("ADAG") == "ADAG.us"   # ADA ⊂ ADAG


def test_actual_crypto_symbols_still_skipped():
    assert _map_to_stooq_symbol("BTC-USD") is None
    assert _map_to_stooq_symbol("BTCUSD") is None
    assert _map_to_stooq_symbol("SOLUSD") is None
    assert _map_to_stooq_symbol("ETH-USD") is None
    assert _map_to_stooq_symbol("DOGE-USDT") is None


def test_existing_exclusions_unchanged():
    assert _map_to_stooq_symbol("^IXIC") == "^ndq"
    assert _map_to_stooq_symbol("600519.SS") is None
    assert _map_to_stooq_symbol("CL=F") is None
    assert _map_to_stooq_symbol("AAPL") == "AAPL.us"
