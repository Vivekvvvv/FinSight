# -*- coding: utf-8 -*-
"""R67：cn_screener._passes_filters 与 us_screener(R66) 同型缺陷——字段缺失
的行在数值约束下被放行：A股停牌票 f2="-" → price=None，"priceMoreThan":"100"
的结果里会混入无价格数据的股票。有阈值时缺失字段应判不通过。"""
from __future__ import annotations

import backend.tools.cn_screener as cs


def test_missing_price_fails_price_filter():
    """停牌/缺数据行 price=None 不满足 "price>100" 也不满足 "price<100"。"""
    item = {"symbol": "600000.SS", "price": None, "market_cap": 1e11, "volume": 1e8}
    assert cs._passes_filters(item, {"priceMoreThan": "100"}) is False
    assert cs._passes_filters(item, {"priceLowerThan": "100"}) is False


def test_missing_market_cap_fails_cap_filter():
    item = {"symbol": "000001.SZ", "price": 12.0, "market_cap": None, "volume": 1e8}
    assert cs._passes_filters(item, {"marketCapMoreThan": "500000000"}) is False
    assert cs._passes_filters(item, {"marketCapLowerThan": "500000000"}) is False


def test_missing_volume_fails_volume_filter():
    item = {"symbol": "0700.HK", "price": 380.0, "market_cap": 3e12, "volume": None}
    assert cs._passes_filters(item, {"volumeMoreThan": "1000"}) is False


def test_present_values_still_filtered_correctly():
    """正常有值的行过滤行为不变——回归保护。"""
    item = {"symbol": "600519.SS", "price": 1700.0, "market_cap": 2e12, "volume": 3e7}
    assert cs._passes_filters(item, {"priceMoreThan": "100"}) is True
    assert cs._passes_filters(item, {"priceLowerThan": "100"}) is False
    assert cs._passes_filters(item, {"marketCapMoreThan": "1000000000000"}) is True
    assert cs._passes_filters(item, {"volumeMoreThan": "1000"}) is True


def test_no_threshold_means_no_constraint():
    """未给阈值时字段缺失不排斥——无约束语义保留。"""
    item = {"symbol": "ANY", "price": None, "market_cap": None, "volume": None}
    assert cs._passes_filters(item, {}) is True
    assert cs._passes_filters(item, {"priceMoreThan": None}) is True
