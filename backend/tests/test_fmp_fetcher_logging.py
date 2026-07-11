# -*- coding: utf-8 -*-
"""R58 回归：FMP 图表 fetcher 失败时打日志，不再静默吞异常。

fetch_segment_mix/fetch_sector_weights/fetch_top_constituents/fetch_holdings
的 except 此前无 logger（全模块唯一），FMP outage 时空图表零诊断信号。
"""
from __future__ import annotations

import logging

import backend.tools.fmp as fmp
from backend.dashboard import data_service as ds


def test_fetch_sector_weights_logs_on_failure(monkeypatch, caplog):
    def _boom(_symbol):
        raise RuntimeError("fmp 502")

    monkeypatch.setattr(fmp, "get_etf_sector_weights", _boom)
    with caplog.at_level(logging.WARNING):
        result = ds.fetch_sector_weights("SPY", "etf")
    assert result == []
    assert any("fetch_sector_weights failed" in r.message for r in caplog.records)


def test_fetch_holdings_logs_on_failure(monkeypatch, caplog):
    def _boom(_symbol, limit=50):
        raise RuntimeError("fmp down")

    monkeypatch.setattr(fmp, "get_etf_holdings", _boom)
    with caplog.at_level(logging.WARNING):
        result = ds.fetch_holdings("SPY", "etf")
    assert result == []
    assert any("fetch_holdings failed" in r.message for r in caplog.records)


def test_fetch_top_constituents_logs_on_failure(monkeypatch, caplog):
    def _boom(_symbol):
        raise RuntimeError("fmp down")

    monkeypatch.setattr(fmp, "get_index_constituents", _boom)
    with caplog.at_level(logging.WARNING):
        result = ds.fetch_top_constituents("^GSPC", "index")
    assert result == []
    assert any("fetch_top_constituents failed" in r.message for r in caplog.records)
