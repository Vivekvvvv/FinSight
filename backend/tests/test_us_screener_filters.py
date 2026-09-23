# -*- coding: utf-8 -*-
"""R66：us_screener._passes_filters 对缺字段 item 放行——item["price"]=None
时 threshold is not None and actual is not None 短路为 False，不过滤直接
通过，"price>100" 的结果里混进无价格数据的股票。缺失字段应判不通过。"""
from __future__ import annotations

import backend.tools.us_screener as us


def test_missing_price_fails_price_filter():
    item = {"symbol": "NOPX", "price": None, "market_cap": 1e9, "volume": 1e6}
    assert us._passes_filters(item, {"priceMoreThan": "100"}) is False
    assert us._passes_filters(item, {"priceLowerThan": "100"}) is False


def test_missing_market_cap_fails_cap_filter():
    item = {"symbol": "NOCAP", "price": 50.0, "market_cap": None, "volume": 1e6}
    assert us._passes_filters(item, {"marketCapMoreThan": "500000000"}) is False


def test_present_values_still_filtered_correctly():
    item = {"symbol": "OK", "price": 150.0, "market_cap": 2e9, "volume": 1e6}
    assert us._passes_filters(item, {"priceMoreThan": "100"}) is True
    assert us._passes_filters(item, {"priceLowerThan": "100"}) is False
    assert us._passes_filters(item, {"marketCapMoreThan": "500000000"}) is True


def test_no_threshold_means_no_constraint():
    """未给阈值时字段缺失不排斥——无约束语义保留。"""
    item = {"symbol": "ANY", "price": None, "market_cap": None, "volume": None}
    assert us._passes_filters(item, {}) is True
    assert us._passes_filters(item, {"priceMoreThan": None}) is True
