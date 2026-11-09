from __future__ import annotations

import types

from backend.tools import financial


def test_nonpositive_earnings_table_limits_return_no_records():
    import pandas as pd
    frame = pd.DataFrame({"estimate": [1.0, 2.0]})
    for limit in (0, -1):
        assert financial._serialize_table_records(frame, max_rows=limit) == []


def test_earnings_estimate_requests_require_normalized_textual_tickers_before_io(monkeypatch):
    calls = []
    monkeypatch.setattr(financial, "yf", types.SimpleNamespace(Ticker=lambda ticker: calls.append(ticker) or types.SimpleNamespace()))
    for ticker in ("  ", True, 123, {}, ["AAPL"]):
        result = financial.get_earnings_estimates(ticker)
        assert result["error"] == "ticker_required"
        assert result["ticker"] == ""
    assert calls == []
    assert financial.get_earnings_estimates(" aapl ")["ticker"] == "AAPL"
    assert calls == ["AAPL"]


def test_invalid_company_queries_stop_before_lookup_providers(monkeypatch):
    _patch_no_other_sources(monkeypatch)
    calls = []
    monkeypatch.setattr(financial, "finnhub_client", types.SimpleNamespace(
        symbol_lookup=lambda company: calls.append(company) or {"result": []}))
    monkeypatch.setattr(financial, "search", lambda *args: calls.append(args) or "")
    for company in ("  ", True, 123, {}, ["Apple"]):
        assert financial.resolve_company_ticker(company)["matches"] == []
    assert calls == []


def test_revision_signal_counts_require_nonnegative_integers():
    invalid = [{"downLast7days": -10}, {"upLast7days": 7.5}, {"upLast30days": True},
               {"upLast7days": 20, "success": False}, {"upLast7days": 20, "status": " Failed "}]
    assert financial._infer_revision_signal(invalid) == "neutral"
    assert financial._infer_revision_signal([*invalid, {"downLast7days": "6"}]) == "negative"


def test_failed_earnings_table_rows_do_not_use_slots_or_supply_revision_signals():
    import pandas as pd
    rows = [{"upLast7days": 20, "success": False},
            {"upLast7days": 20, "error": "bad"},
            {"upLast7days": 20, "status": " Failed "},
            {"downLast7days": 10}]
    frame = pd.DataFrame(rows, index=["bad1", "bad2", "bad3", "valid"], dtype=object)
    result = financial._serialize_table_records(frame, max_rows=1)
    assert len(result) == 1 and result[0]["period"] == "valid"
    assert financial._infer_revision_signal(result) == "negative"


def test_sec_financial_tables_only_use_finite_numeric_evidence():
    payload = {"ticker": "AAPL", "periods": ["2025Q1", "2024Q4"],
               "revenue": ["100", "90"], "eps": ["inf", "1.5"], "net_income": [{"bad": True}, True]}
    result = financial._convert_sec_companyfacts_payload(payload)
    income = result["financials"]
    assert income["index"] == ["Total Revenue", "Basic EPS"]
    assert income["data"] == [{"2025-03-31": 100.0, "2024-12-31": 90.0},
                               {"2025-03-31": None, "2024-12-31": 1.5}]


def test_sec_financial_period_filter_preserves_metric_alignment_and_latest_order():
    payload = {"ticker": "AAPL", "periods": [None, "2024Q4", "2025Q1", "bad", "2025Q1"],
               "revenue": [999, 90, 100, 888, 110]}
    result = financial._convert_sec_companyfacts_payload(payload)
    assert result["financials"]["columns"] == ["2025-03-31", "2024-12-31"]
    assert result["financials"]["data"] == [{"2025-03-31": 110.0, "2024-12-31": 90.0}]
    assert payload["revenue"] == [999, 90, 100, 888, 110]


def test_sec_financial_fallback_cannot_return_another_companys_tables(monkeypatch):
    from backend.tools import sec
    for identity in ({"ticker": "MSFT"}, {"symbol": "MSFT"}, {"ticker": "AAPL", "symbol": "MSFT"}):
        payload = {**identity, "periods": ["2025Q1"], "revenue": [100]}
        monkeypatch.setattr(sec, "get_sec_company_facts_quarterly", lambda *args, **kwargs: payload)
        assert financial._fetch_financials_from_sec_companyfacts("AAPL") is None
    payload = {"ticker": " aapl ", "periods": ["2025Q1"], "revenue": [100]}
    assert financial._fetch_financials_from_sec_companyfacts("AAPL")["ticker"] == "AAPL"


def test_failed_sec_companyfacts_payload_cannot_become_successful_financial_tables():
    for failure in ({"success": False}, {"status": " Unavailable "}):
        payload = {"ticker": "AAPL", "periods": ["2025Q1"], "revenue": [100], **failure}
        assert financial._convert_sec_companyfacts_payload(payload) is None


def test_nonpositive_company_lookup_limits_do_not_call_any_provider(monkeypatch):
    _patch_no_other_sources(monkeypatch)
    calls = []
    monkeypatch.setattr(financial, "OPENFIGI_API_KEY", "test")
    monkeypatch.setattr(financial, "EODHD_API_KEY", "test")
    monkeypatch.setattr(financial, "_http_post", lambda *args, **kwargs: calls.append("openfigi") or _LookupResp({"data": [{"ticker": "AAPL"}]}))
    monkeypatch.setattr(financial, "_http_get", lambda *args, **kwargs: calls.append("eodhd") or _LookupResp([{"Code": "AAPL"}]))
    monkeypatch.setattr(financial, "finnhub_client", types.SimpleNamespace(
        symbol_lookup=lambda company: calls.append("finnhub") or {"result": [{"symbol": "AAPL"}]}))
    monkeypatch.setattr(financial, "search", lambda *args: calls.append("search") or "AAPL")
    for limit in (0, -1):
        assert financial.resolve_company_ticker("Apple", limit)["matches"] == []
        assert financial._openfigi_symbol_lookup("Apple", limit) == []
        assert financial._eodhd_symbol_lookup("Apple", limit) == []
    assert calls == []


def test_openfigi_limits_unique_successful_results_after_filtering(monkeypatch):
    _patch_no_other_sources(monkeypatch)
    monkeypatch.setattr(financial, "OPENFIGI_API_KEY", "test")
    rows = [{"ticker": "BAD", "success": False}, {"ticker": " aapl "},
            {"ticker": "AAPL"}, {"ticker": "MSFT"}, {"ticker": "TSLA"}]
    monkeypatch.setattr(financial, "_http_post", lambda *args, **kwargs: _LookupResp({"data": rows}))
    assert [item["symbol"] for item in financial._openfigi_symbol_lookup("Technology", limit=2)] == ["AAPL", "MSFT"]


def test_eodhd_applies_limit_after_filtering_and_normalizing_matches(monkeypatch):
    _patch_no_other_sources(monkeypatch)
    monkeypatch.setattr(financial, "EODHD_API_KEY", "test")
    rows = [{"Code": "BAD", "success": False}] * 6 + [
        {"Code": " aapl ", "Exchange": "US"}, {"Code": "AAPL", "Exchange": "us"},
        {"Code": "MSFT", "Exchange": "US"}, {"Code": "TSLA", "Exchange": "US"}]
    monkeypatch.setattr(financial, "_http_get", lambda *args, **kwargs: _LookupResp(rows))
    assert [item["symbol"] for item in financial._eodhd_symbol_lookup("Technology", limit=2)] == ["AAPL.US", "MSFT.US"]


def test_eodhd_skips_failed_and_nontext_codes_without_losing_later_matches(monkeypatch):
    _patch_no_other_sources(monkeypatch)
    monkeypatch.setattr(financial, "EODHD_API_KEY", "test")
    rows = [{"Code": "BAD", "Exchange": "US", "success": False},
            {"Code": "BAD2", "status": " Failed "}, {"Code": "BAD3", "error": "bad"},
            {"Code": ["bad"], "Exchange": "US"}, {"Code": True}, {"Code": 123},
            {"Code": "  "}, {"Code": " aapl ", "Exchange": " nasdaq "}]
    monkeypatch.setattr(financial, "_http_get", lambda *args, **kwargs: _LookupResp(rows))
    assert [item["symbol"] for item in financial._eodhd_symbol_lookup("Apple", limit=10)] == ["AAPL.NASDAQ"]


def test_openfigi_filters_failed_or_nontext_tickers_before_returning_results(monkeypatch):
    _patch_no_other_sources(monkeypatch)
    monkeypatch.setattr(financial, "OPENFIGI_API_KEY", "test")
    rows = [{"ticker": "BAD", "success": False}, {"ticker": "BAD2", "status": " Unavailable "},
            {"ticker": "BAD3", "error": "bad"}, {"ticker": True}, {"ticker": ["bad"]},
            {"ticker": "  "}, {"ticker": " aapl "}]
    monkeypatch.setattr(financial, "_http_post", lambda *args, **kwargs: _LookupResp({"data": rows}))
    assert [item["symbol"] for item in financial._openfigi_symbol_lookup("Apple")] == ["AAPL"]


def test_failed_openfigi_envelope_cannot_supply_matches(monkeypatch):
    _patch_no_other_sources(monkeypatch)
    monkeypatch.setattr(financial, "OPENFIGI_API_KEY", "test")
    for failure in ({"error": "failed"}, {"success": False}, {"status": " Failed "}):
        monkeypatch.setattr(financial, "_http_post", lambda *args, **kwargs: _LookupResp({
            **failure, "data": [{"ticker": "AAPL"}]}))
        assert financial._openfigi_symbol_lookup("Apple") == []


def test_failed_finnhub_lookup_rows_cannot_displace_valid_matches(monkeypatch):
    _patch_no_other_sources(monkeypatch)
    monkeypatch.setattr(financial, "finnhub_client", types.SimpleNamespace(symbol_lookup=lambda company: {
        "result": [{"symbol": "BAD1", "success": False}, {"symbol": "BAD2", "error": "failed"},
                   {"symbol": "BAD3", "status": " Failed "}, {"symbol": "AAPL"}]}))
    result = financial.resolve_company_ticker("Apple", limit=1)
    assert [item["symbol"] for item in result["matches"]] == ["AAPL"]


def test_failed_finnhub_lookup_envelope_cannot_supply_ticker_matches(monkeypatch):
    _patch_no_other_sources(monkeypatch)
    for failure in ({"error": "failed"}, {"success": False}, {"status": " Unavailable "}):
        monkeypatch.setattr(financial, "finnhub_client", types.SimpleNamespace(symbol_lookup=lambda company: {
            **failure, "result": [{"symbol": "AAPL"}]}))
        assert financial.resolve_company_ticker("Apple")["matches"] == []


def test_resolve_ticker_normalizes_symbols_before_deduplication(monkeypatch):
    _patch_no_other_sources(monkeypatch)
    monkeypatch.setattr(financial, "finnhub_client", types.SimpleNamespace(symbol_lookup=lambda company: {
        "result": [{"symbol": " aapl "}, {"symbol": "AAPL"}, {"symbol": "msft"}]}))
    result = financial.resolve_company_ticker("Technology")
    assert [item["symbol"] for item in result["matches"]] == ["AAPL", "MSFT"]


def test_resolve_ticker_skips_nontext_symbols_without_losing_valid_matches(monkeypatch):
    _patch_no_other_sources(monkeypatch)
    monkeypatch.setattr(financial, "finnhub_client", types.SimpleNamespace(symbol_lookup=lambda company: {
        "result": [{"symbol": ["bad"]}, {"symbol": {"bad": True}}, {"symbol": True},
                   {"symbol": 123}, {"symbol": "  "}, {"symbol": "AAPL"}]}))
    result = financial.resolve_company_ticker("Apple")
    assert [item["symbol"] for item in result["matches"]] == ["AAPL"]
    assert result["source"] == "finnhub"


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
