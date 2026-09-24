from __future__ import annotations

import types

from backend.tools import financial


def test_convert_sec_companyfacts_payload_builds_agent_tables():
    payload = {
        "ticker": "MSFT",
        "periods": ["2025Q3", "2025Q2"],
        "revenue": [70.0, 65.0],
        "gross_profit": [48.0, 44.0],
        "operating_income": [30.0, 27.0],
        "net_income": [24.0, 22.0],
        "eps": [3.2, 3.0],
        "total_assets": [510.0, 500.0],
        "total_liabilities": [210.0, 205.0],
        "operating_cash_flow": [28.0, 26.0],
        "free_cash_flow": [22.0, 20.0],
        "error": None,
    }

    converted = financial._convert_sec_companyfacts_payload(payload)
    assert isinstance(converted, dict)
    assert converted.get("source") == "sec_companyfacts"
    assert converted.get("error") is None

    income = converted.get("financials") or {}
    assert income.get("columns") == ["2025-09-30", "2025-06-30"]
    assert "Total Revenue" in (income.get("index") or [])
    assert "Operating Income" in (income.get("index") or [])

    balance = converted.get("balance_sheet") or {}
    assert "Total Assets" in (balance.get("index") or [])
    assert "Total Liabilities" in (balance.get("index") or [])

    cashflow = converted.get("cashflow") or {}
    assert "Operating Cash Flow" in (cashflow.get("index") or [])
    assert "Free Cash Flow" in (cashflow.get("index") or [])


def test_get_financial_statements_uses_sec_fallback_when_yfinance_empty(monkeypatch):
    class EmptyTicker:
        def __init__(self, _ticker: str):
            self.financials = None
            self.income_stmt = None
            self.quarterly_financials = None
            self.quarterly_income_stmt = None
            self.balance_sheet = None
            self.quarterly_balance_sheet = None
            self.cashflow = None
            self.quarterly_cashflow = None

    monkeypatch.setattr(financial, "yf", types.SimpleNamespace(Ticker=EmptyTicker))
    monkeypatch.setattr(
        financial,
        "_fetch_financials_from_sec_companyfacts",
        lambda _ticker: {
            "ticker": "MSFT",
            "timestamp": "2026-02-24T00:00:00",
            "financials": {"columns": ["2025-09-30"], "index": ["Total Revenue"], "data": [{"2025-09-30": 70.0}]},
            "balance_sheet": None,
            "cashflow": None,
            "error": None,
            "warnings": ["fallback:sec_companyfacts"],
            "source": "sec_companyfacts",
        },
    )

    result = financial.get_financial_statements("MSFT")
    assert isinstance(result, dict)
    assert result.get("source") == "sec_companyfacts"
    assert result.get("error") is None
    assert "fallback:sec_companyfacts" in (result.get("warnings") or [])


def test_get_financial_statements_returns_error_when_all_sources_fail(monkeypatch):
    class EmptyTicker:
        def __init__(self, _ticker: str):
            self.financials = None
            self.income_stmt = None
            self.quarterly_financials = None
            self.quarterly_income_stmt = None
            self.balance_sheet = None
            self.quarterly_balance_sheet = None
            self.cashflow = None
            self.quarterly_cashflow = None

    monkeypatch.setattr(financial, "yf", types.SimpleNamespace(Ticker=EmptyTicker))
    monkeypatch.setattr(financial, "_fetch_financials_from_sec_companyfacts", lambda _ticker: None)

    result = financial.get_financial_statements("MSFT")
    assert isinstance(result, dict)
    assert result.get("source") != "sec_companyfacts"
    assert isinstance(result.get("error"), str) and result.get("error")


def test_get_financial_statements_redacts_top_level_exception(monkeypatch, caplog):
    sentinel = "PRIVATE_FINANCIAL_PROVIDER_DETAIL"

    class FailingTicker:
        def __init__(self, _ticker: str):
            raise RuntimeError(sentinel)

    monkeypatch.setattr(financial, "yf", types.SimpleNamespace(Ticker=FailingTicker))
    monkeypatch.setattr(financial, "_fetch_financials_from_sec_companyfacts", lambda _ticker: None)

    result = financial.get_financial_statements("MSFT")

    assert result["error"] == "获取财报数据失败"
    assert result["warnings"] == ["RuntimeError"]
    assert sentinel not in str(result)
    assert sentinel not in caplog.text


def test_get_financial_statements_redacts_partial_table_warnings(monkeypatch, caplog):
    sentinel = "PRIVATE_FINANCIAL_TABLE_DETAIL"

    class FailingTicker:
        def __init__(self, _ticker: str):
            pass

        def __getattr__(self, _name):
            raise RuntimeError(sentinel)

    monkeypatch.setattr(financial, "yf", types.SimpleNamespace(Ticker=FailingTicker))
    monkeypatch.setattr(financial, "_fetch_financials_from_sec_companyfacts", lambda _ticker: None)

    result = financial.get_financial_statements("MSFT")

    assert result["warnings"]
    assert all(item.endswith(":RuntimeError") for item in result["warnings"])
    assert sentinel not in str(result)
    assert sentinel not in caplog.text


# ── R115：ticker 解析各数据源毒条目按条跳过 ──────────────────────────


class _LookupResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _patch_no_other_sources(monkeypatch):
    monkeypatch.setattr(financial, "OPENFIGI_API_KEY", "")
    monkeypatch.setattr(financial, "EODHD_API_KEY", "")
    monkeypatch.setattr(financial, "finnhub_client", None)
    monkeypatch.setattr(financial, "search", lambda *a, **k: "")


def test_resolve_ticker_finnhub_skips_poison_items(monkeypatch):
    """R115：finnhub symbol_lookup 混入非 dict 条目——item.get 的
    AttributeError 落进源级 except，该源已收集 matches 全丢退到 search。"""
    _patch_no_other_sources(monkeypatch)
    monkeypatch.setattr(
        financial,
        "finnhub_client",
        types.SimpleNamespace(
            symbol_lookup=lambda _q: {
                "result": [
                    {
                        "displaySymbol": "AAPL",
                        "description": "Apple Inc",
                        "type": "Common Stock",
                        "primaryExchange": "NASDAQ",
                    },
                    "junk-entry",
                    None,
                ]
            }
        ),
    )

    res = financial.resolve_company_ticker("apple")

    assert res["source"] == "finnhub", "毒条目不得把 finnhub 源整体丢弃"
    assert [m["symbol"] for m in res["matches"]] == ["AAPL"]


def test_resolve_ticker_openfigi_skips_poison_items(monkeypatch):
    """R115 同缺陷类：openfigi data 混入非 dict 条目——.get AttributeError
    逃逸出 _openfigi_symbol_lookup 被调用方 except 吞掉，整源丢失。"""
    _patch_no_other_sources(monkeypatch)
    monkeypatch.setattr(financial, "OPENFIGI_API_KEY", "key")
    monkeypatch.setattr(
        financial,
        "_http_post",
        lambda *a, **k: _LookupResp(
            {
                "data": [
                    {"ticker": "AAPL", "name": "Apple", "exchCode": "US"},
                    "junk-entry",
                    None,
                ]
            }
        ),
    )

    res = financial.resolve_company_ticker("apple")

    assert res["source"] == "openfigi", "毒条目不得把 openfigi 源整体丢弃"
    assert [m["symbol"] for m in res["matches"]] == ["AAPL"]


def test_resolve_ticker_eodhd_skips_poison_items(monkeypatch):
    """R115 同缺陷类：eodhd list 混入非 dict 条目 → 整源丢失退到 search。"""
    _patch_no_other_sources(monkeypatch)
    monkeypatch.setattr(financial, "EODHD_API_KEY", "key")
    monkeypatch.setattr(
        financial,
        "_http_get",
        lambda *a, **k: _LookupResp(
            [
                {"Code": "AAPL", "Exchange": "NASDAQ", "Name": "Apple"},
                42,
                None,
            ]
        ),
    )

    res = financial.resolve_company_ticker("apple")

    assert res["source"] == "eodhd", "毒条目不得把 eodhd 源整体丢弃"
    assert [m["symbol"] for m in res["matches"]] == ["AAPL.NASDAQ"]
