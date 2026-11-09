from __future__ import annotations

import sys
import types

import pandas as pd
import pytest

from backend.dashboard import data_service
from backend.dashboard import data_fetchers
from backend.dashboard import data_fetchers_equity
from backend.dashboard import peer_service


def test_unsuffixed_mainland_stock_codes_use_cn_peer_defaults_without_us_lookup(monkeypatch):
    calls = []
    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(
        Ticker=lambda symbol: calls.append(symbol) or types.SimpleNamespace(info={})))
    assert peer_service._infer_market_from_symbol(" 600519 ") == "CN"
    peers = peer_service.resolve_peers("600519", limit=3)
    assert all(symbol.endswith((".SS", ".SZ")) for symbol in peers)
    assert "600519.SS" not in peers
    assert calls == []


@pytest.mark.parametrize("provider", ["yfinance", "finnhub", "cn_hk"])
@pytest.mark.parametrize("name", [42, {"bad": True}, ["bad"], "  "])
def test_peer_names_require_nonempty_text_and_preserve_metrics(monkeypatch, provider, name):
    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=lambda symbol:
                        types.SimpleNamespace(info={"shortName": name, "longName": "Apple", "trailingPE": 20})))
    monkeypatch.setattr(peer_service, "_finnhub_request", lambda path, params:
                        {"name": name} if path == "stock/profile2" else {"metric": {"peTTM": 20}})
    import backend.tools.cn_hk_market as market
    monkeypatch.setattr(market, "fetch_cn_hk_quote_metrics", lambda sym: {"name": name, "trailing_pe": 20})
    if provider == "yfinance":
        result = peer_service._fetch_single_peer_metrics("AAPL")
        assert result["name"] == "Apple"
    elif provider == "finnhub":
        result = peer_service._fetch_single_peer_metrics_from_finnhub("AAPL")
        assert result["name"] == "AAPL"
    else:
        result = peer_service._fetch_single_peer_metrics_from_cn_hk("0700.HK")
        assert result["name"] == "0700.HK"
    assert result["trailing_pe"] == 20


@pytest.mark.parametrize("provider", ["yfinance", "finnhub", "cn_hk"])
@pytest.mark.parametrize("yield_value", [-0.1, 0, 0.02])
def test_peer_dividend_yields_keep_valid_ratios_and_omit_negative_values(monkeypatch, provider, yield_value):
    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=lambda symbol:
                        types.SimpleNamespace(info={"dividendYield": yield_value, "trailingPE": 20})))
    monkeypatch.setattr(peer_service, "_finnhub_request", lambda path, params:
                        {} if path == "stock/profile2" else {"metric": {"peTTM": 20,
                        "dividendYieldIndicatedAnnual": yield_value * 100}})
    import backend.tools.cn_hk_market as market
    monkeypatch.setattr(market, "fetch_cn_hk_quote_metrics",
                        lambda sym: {"dividend_yield": yield_value, "trailing_pe": 20})
    if provider == "yfinance":
        result = peer_service._fetch_single_peer_metrics("AAPL")
    elif provider == "finnhub":
        result = peer_service._fetch_single_peer_metrics_from_finnhub("AAPL")
    else:
        result = peer_service._fetch_single_peer_metrics_from_cn_hk("0700.HK")
    assert result["dividend_yield"] == (yield_value if yield_value >= 0 else None)
    assert result["trailing_pe"] == 20
    assert peer_service._has_peer_metrics({"dividend_yield": yield_value}) == (yield_value >= 0)


@pytest.mark.parametrize("provider", ["yfinance", "cn_hk"])
@pytest.mark.parametrize("market_cap", [-1, 0])
def test_invalid_peer_market_cap_is_omitted_when_other_metrics_are_valid(monkeypatch, provider, market_cap):
    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=lambda symbol:
                        types.SimpleNamespace(info={"marketCap": market_cap, "trailingPE": 20})))
    import backend.tools.cn_hk_market as market
    monkeypatch.setattr(market, "fetch_cn_hk_quote_metrics",
                        lambda sym: {"market_cap": market_cap, "trailing_pe": 20})
    result = (peer_service._fetch_single_peer_metrics("AAPL") if provider == "yfinance"
              else peer_service._fetch_single_peer_metrics_from_cn_hk("0700.HK"))
    assert result["trailing_pe"] == 20
    assert result["market_cap"] is None


@pytest.mark.parametrize("provider", ["yfinance", "finnhub", "cn_hk"])
@pytest.mark.parametrize("market_cap", [-1, 0])
def test_nonpositive_peer_market_caps_cannot_claim_available_metrics(monkeypatch, provider, market_cap):
    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=lambda symbol:
                        types.SimpleNamespace(info={"marketCap": market_cap})))
    monkeypatch.setattr(peer_service, "_fetch_single_peer_metrics_from_finnhub", lambda sym: None)
    import backend.tools.cn_hk_market as market
    monkeypatch.setattr(market, "fetch_cn_hk_quote_metrics", lambda sym: {"market_cap": market_cap})
    assert not peer_service._has_peer_metrics({"market_cap": market_cap})
    if provider == "cn_hk":
        assert peer_service._fetch_single_peer_metrics_from_cn_hk("0700.HK") is None
    else:
        assert not peer_service._has_peer_metrics(peer_service._fetch_single_peer_metrics("AAPL"))
    assert peer_service._has_peer_metrics({"market_cap": 10})


@pytest.mark.parametrize("failure", [{"success": False}, {"error": "bad"}, {"status": " Failed "}])
def test_failed_nested_finnhub_peer_metrics_cannot_publish_comparison_values(monkeypatch, failure):
    profile = {"marketCapitalization": 10}
    metrics = {"peTTM": 20, "roeTTM": 15, **failure}
    monkeypatch.setattr(peer_service, "_finnhub_request", lambda path, params:
                        profile if path == "stock/profile2" else {"metric": metrics})
    result = peer_service._fetch_single_peer_metrics_from_finnhub("AAPL")
    assert result["market_cap"] == 10_000_000
    assert result["trailing_pe"] is None and result["roe"] is None
    profile.clear()
    assert peer_service._fetch_single_peer_metrics_from_finnhub("AAPL") is None


@pytest.mark.parametrize("failure", [{"success": False}, {"status": " Failed "}, {"error": "not a peer"}])
def test_failed_screener_rows_cannot_occupy_the_peer_limit(monkeypatch, failure):
    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(
        Ticker=lambda symbol: types.SimpleNamespace(info={"industry": "Technology"})))
    import backend.tools.fmp as fmp
    monkeypatch.setattr(fmp, "_fmp_request", lambda *args, **kwargs:
                        [{"symbol": "BAD", **failure}, {"symbol": "MSFT"}])
    assert peer_service.resolve_peers("AAPL", limit=1) == ["MSFT"]


@pytest.mark.parametrize("marker", [{"success": False}, {"status": "failed"}, {"symbol": "OTHER"}])
def test_invalid_company_classification_cannot_select_a_wrong_peer_group(monkeypatch, marker):
    info = {"industry": "Automotive", "sector": "Consumer Cyclical", **marker}
    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=lambda symbol: types.SimpleNamespace(info=info)))
    import backend.tools.fmp as fmp
    monkeypatch.setattr(fmp, "_fmp_request", lambda *args, **kwargs: None)
    assert peer_service.resolve_peers("UNKNOWN", limit=2) == ["AAPL", "MSFT"]


@pytest.mark.parametrize("labels", [{"industry": ["bad"]}, {"sector": {"bad": True}}])
def test_malformed_peer_classifications_fall_back_to_market_defaults(monkeypatch, labels):
    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=lambda symbol: types.SimpleNamespace(info=labels)))
    import backend.tools.fmp as fmp
    monkeypatch.setattr(fmp, "_fmp_request", lambda *args, **kwargs: None)
    assert peer_service.resolve_peers("UNKNOWN", limit=2) == ["AAPL", "MSFT"]


@pytest.mark.parametrize("status", ["failed", " Error ", "unavailable"])
def test_failed_peer_results_cannot_make_comparison_appear_available(monkeypatch, status):
    monkeypatch.setattr(peer_service, "_fetch_single_peer_metrics",
                        lambda sym: {"symbol": sym, "status": status, "trailing_pe": 99})
    assert peer_service.fetch_peer_comparison("AAPL", peers=[]) is None


@pytest.mark.parametrize("primary", [-100.0, 1e308])
def test_peer_market_cap_recovers_when_profile_value_is_unusable(monkeypatch, primary):
    monkeypatch.setattr(peer_service, "_finnhub_request", lambda path, params:
                        {"marketCapitalization": primary} if path == "stock/profile2"
                        else {"metric": {"marketCapitalization": 100.0}})
    row = peer_service._fetch_single_peer_metrics_from_finnhub("AAPL")
    assert row["market_cap"] == 100_000_000.0


@pytest.mark.parametrize("path", ["stock/profile2", "stock/metric"])
@pytest.mark.parametrize("field", ["symbol", "ticker"])
def test_finnhub_peer_components_cannot_mix_in_another_instrument(monkeypatch, path, field):
    def request(route, params):
        row = {"name": "Apple", "marketCapitalization": 10} if route == "stock/profile2" else {"metric": {"peTTM": 20}}
        if route == path:
            row[field] = "MSFT"
        return row
    monkeypatch.setattr(peer_service, "_finnhub_request", request)
    assert peer_service._fetch_single_peer_metrics_from_finnhub("AAPL") is None


@pytest.mark.parametrize("failure", [{"success": False}, {"status": " Failed "}, {"status": "UNAVAILABLE"}])
def test_peer_finnhub_http_success_cannot_hide_business_failure(monkeypatch, failure):
    import backend.tools.env as env
    import backend.tools.http as http
    monkeypatch.setattr(env, "FINNHUB_API_KEY", "test-token")
    monkeypatch.setattr(http, "_http_get", lambda *args, **kwargs: types.SimpleNamespace(
        status_code=200, json=lambda: {"metric": {"peTTM": 99}, **failure}))
    assert peer_service._finnhub_request("stock/metric") is None


@pytest.mark.parametrize("status", ["failed", " Error ", "UNAVAILABLE"])
def test_cn_hk_failed_status_cannot_supply_peer_valuation(monkeypatch, status):
    import backend.tools.cn_hk_market as market
    monkeypatch.setattr(market, "fetch_cn_hk_quote_metrics",
                        lambda sym: {"symbol": sym, "status": status, "trailing_pe": 99.0})
    assert peer_service._fetch_single_peer_metrics_from_cn_hk("0700.HK") is None


@pytest.mark.parametrize("field", ["symbol", "ticker"])
def test_yfinance_peer_metrics_for_another_stock_cannot_replace_fallback(monkeypatch, field):
    info = {"trailingPE": 99.0, field: "MSFT"}
    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=lambda symbol: types.SimpleNamespace(info=info)))
    monkeypatch.setattr(peer_service, "_fetch_single_peer_metrics_from_finnhub",
                        lambda sym: {"symbol": sym, "trailing_pe": 20.0})
    assert peer_service._fetch_single_peer_metrics("AAPL")["trailing_pe"] == 20.0


@pytest.mark.parametrize("failure", [{"status": " Failed "}, {"success": False}, {"error": "stale"}])
def test_yfinance_failed_peer_metrics_fall_back_instead_of_appearing_live(monkeypatch, failure):
    info = {"trailingPE": 99.0, **failure}
    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=lambda symbol: types.SimpleNamespace(info=info)))
    monkeypatch.setattr(peer_service, "_fetch_single_peer_metrics_from_finnhub",
                        lambda sym: {"symbol": sym, "trailing_pe": 20.0})
    assert peer_service._fetch_single_peer_metrics("AAPL")["trailing_pe"] == 20.0


@pytest.mark.parametrize("primary, expected", [(0.0, 0.0), ("bad", 20.0), (float("nan"), 20.0)])
def test_dashboard_pe_aliases_preserve_valid_primary_and_recover_invalid_values(monkeypatch, primary, expected):
    from backend.dashboard import data_providers

    monkeypatch.setattr(data_providers, "_finnhub_request", lambda path, params:
                        {"metric": {"peTTM": primary, "peBasicExclExtraTTM": 20.0,
                                    "forwardPE": primary, "peExclExtraAnnual": 20.0}})
    result = data_providers._fetch_valuation_from_finnhub("AAPL")
    assert result["trailing_pe"] == expected
    assert result["forward_pe"] == expected


@pytest.mark.parametrize("primary", [None, "bad", 1e308])
def test_dashboard_market_cap_recovers_from_metric_when_profile_cap_unusable(monkeypatch, primary):
    from backend.dashboard import data_providers

    monkeypatch.setattr(data_providers, "_finnhub_request", lambda path, params:
                        {"marketCapitalization": primary} if path == "stock/profile2"
                        else {"metric": {"marketCapitalization": 100.0}})
    result = data_providers._fetch_valuation_from_finnhub("AAPL")
    assert result is not None
    assert result["market_cap"] == 100_000_000.0


def test_dashboard_finnhub_request_rejects_business_failure(monkeypatch):
    from backend.dashboard import data_providers
    from backend.tools import env, http

    monkeypatch.setattr(env, "FINNHUB_API_KEY", "test")
    monkeypatch.setattr(http, "_http_get", lambda *args, **kwargs: types.SimpleNamespace(
        status_code=200, json=lambda: {"success": False, "metric": {"peTTM": 20.0}},
    ))
    assert data_providers._finnhub_request("stock/metric") is None


@pytest.mark.parametrize("marker", [{"success": False}, {"error": "failed"}])
def test_dashboard_cn_hk_valuation_rejects_failed_payloads(monkeypatch, marker):
    from backend.dashboard import data_providers
    from backend.tools import cn_hk_market

    monkeypatch.setattr(cn_hk_market, "fetch_cn_hk_quote_metrics", lambda _symbol: {
        **marker, "trailing_pe": 20.0,
    })
    assert data_providers._fetch_valuation_from_cn_hk_market("0700.HK") is None


@pytest.mark.parametrize("field", ["ticker", "symbol"])
def test_dashboard_cn_hk_valuation_rejects_mismatched_symbols(monkeypatch, field):
    from backend.dashboard import data_providers
    from backend.tools import cn_hk_market

    monkeypatch.setattr(cn_hk_market, "fetch_cn_hk_quote_metrics", lambda _symbol: {
        field: "9988.HK", "trailing_pe": 20.0,
    })
    assert data_providers._fetch_valuation_from_cn_hk_market("0700.HK") is None


def test_dashboard_sec_statements_reject_business_failure(monkeypatch):
    from backend.dashboard import data_providers
    from backend.tools import sec

    monkeypatch.setattr(sec, "get_sec_company_facts_quarterly", lambda *args, **kwargs: {
        "success": False, "periods": ["2025Q1"], "revenue": [100.0],
    })
    assert data_providers._fetch_financial_statements_from_sec_companyfacts("AAPL") is None


@pytest.mark.parametrize("marker", [{"success": False}, {"error": "failed"}])
def test_dashboard_cn_hk_statements_reject_failed_payloads(monkeypatch, marker):
    from backend.dashboard import data_providers
    from backend.tools import cn_hk_market

    monkeypatch.setattr(cn_hk_market, "fetch_cn_hk_financial_statements", lambda *args, **kwargs: {
        **marker, "periods": ["2025Q1"], "revenue": [100.0],
    })
    assert data_providers._fetch_financial_statements_from_cn_hk_market("0700.HK") is None


@pytest.mark.parametrize("field", ["ticker", "symbol"])
def test_dashboard_sec_statements_require_matching_identity(monkeypatch, field):
    from backend.dashboard import data_providers
    from backend.tools import sec

    monkeypatch.setattr(sec, "get_sec_company_facts_quarterly", lambda *args, **kwargs: {
        field: "MSFT", "periods": ["2025Q1"], "revenue": [100.0],
    })
    assert data_providers._fetch_financial_statements_from_sec_companyfacts("AAPL") is None


@pytest.mark.parametrize("field", ["ticker", "symbol"])
def test_dashboard_cn_hk_statements_require_matching_identity(monkeypatch, field):
    from backend.dashboard import data_providers
    from backend.tools import cn_hk_market

    monkeypatch.setattr(cn_hk_market, "fetch_cn_hk_financial_statements", lambda *args, **kwargs: {
        field: "9988.HK", "periods": ["2025Q1"], "revenue": [100.0],
    })
    assert data_providers._fetch_financial_statements_from_cn_hk_market("0700.HK") is None


def test_dashboard_finnhub_derived_cash_flow_rejects_overflow(monkeypatch):
    import json
    from backend.dashboard import data_providers

    monkeypatch.setattr(data_providers, "_finnhub_request", lambda *args, **kwargs: {"data": [{
        "year": 2025, "quarter": 1, "report": {"cf": [
            {"concept": "us-gaap_NetCashProvidedByUsedInOperatingActivities", "value": -1e308},
            {"concept": "us-gaap_PaymentsToAcquirePropertyPlantAndEquipment", "value": 1e308},
        ]},
    }]})
    result = data_providers._fetch_financial_statements_from_finnhub("AAPL")
    assert result["operating_cash_flow"] == [-1e308]
    assert result["free_cash_flow"] == [None]
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("year, quarter", [(2025, 5), (2025, -1), (2025, 1.5), (2025.5, 1), (10000, 1)])
def test_dashboard_finnhub_report_periods_must_be_valid(monkeypatch, year, quarter):
    from backend.dashboard import data_providers

    report = {"ic": [{"concept": "us-gaap_Revenue", "value": 100.0}]}
    monkeypatch.setattr(data_providers, "_finnhub_request", lambda *args, **kwargs: {"data": [
        {"year": year, "quarter": quarter, "report": report},
        {"year": 2024, "quarter": 4, "report": report},
    ]})
    result = data_providers._fetch_financial_statements_from_finnhub("AAPL")
    assert result["periods"] == ["2024Q4"]


def test_report_exact_concepts_outrank_earlier_partial_labels():
    from backend.dashboard import data_providers

    rows = [
        {"label": "Deferred revenue", "concept": "us-gaap_DeferredRevenue", "value": 1.0},
        {"label": "Total revenue", "concept": "us-gaap_Revenue", "value": 100.0},
    ]
    assert data_providers._match_report_value(rows, label_terms=("revenue",), concept_terms=("revenue",)) == 100.0


@pytest.mark.parametrize("periods", [0, -1])
def test_dashboard_finnhub_empty_period_requests_do_not_fetch(monkeypatch, periods):
    from backend.dashboard import data_providers

    calls = []
    monkeypatch.setattr(data_providers, "_finnhub_request", lambda *args, **kwargs: calls.append(args))
    assert data_providers._fetch_financial_statements_from_finnhub("AAPL", periods=periods) is None
    assert calls == []


@pytest.mark.parametrize("endpoint", ["stock/profile2", "stock/metric"])
@pytest.mark.parametrize("field", ["ticker", "symbol"])
def test_dashboard_finnhub_valuation_requires_matching_payload_identities(monkeypatch, endpoint, field):
    from backend.dashboard import data_providers

    def request(path, params):
        payload = {"marketCapitalization": 100.0} if path == "stock/profile2" else {"metric": {"peTTM": 20.0}}
        if path == endpoint:
            payload[field] = "MSFT"
        return payload
    monkeypatch.setattr(data_providers, "_finnhub_request", request)
    assert data_providers._fetch_valuation_from_finnhub("AAPL") is None


@pytest.mark.parametrize("scope", ["payload", "row"])
def test_dashboard_finnhub_statements_require_matching_identities(monkeypatch, scope):
    from backend.dashboard import data_providers

    row = {"year": 2025, "quarter": 1, "report": {"ic": [{"concept": "us-gaap_Revenue", "value": 100.0}]}}
    payload = {"data": [row]}
    (payload if scope == "payload" else row)["symbol"] = "MSFT"
    monkeypatch.setattr(data_providers, "_finnhub_request", lambda *args, **kwargs: payload)
    assert data_providers._fetch_financial_statements_from_finnhub("AAPL") is None


def test_dashboard_finnhub_market_cap_overflow_is_unavailable():
    from backend.dashboard import data_providers

    assert data_providers._finnhub_market_cap_to_usd(1e308) is None
    assert data_providers._finnhub_market_cap_to_usd(100.0) == 100_000_000.0


@pytest.mark.parametrize("marker", [{"symbol": "MSFT"}, {"symbol": "AAPL", "success": False}, {"symbol": "AAPL", "error": "failed"}])
def test_comparison_does_not_publish_unusable_worker_results(monkeypatch, marker):
    monkeypatch.setattr(peer_service, "_fetch_single_peer_metrics", lambda symbol: {**marker, "trailing_pe": 20.0})
    assert peer_service.fetch_peer_comparison("AAPL", peers=[]) is None


@pytest.mark.parametrize("field", ["symbol", "ticker"])
def test_cn_hk_peer_metrics_reject_another_instruments_payload(monkeypatch, field):
    from backend.tools import cn_hk_market
    monkeypatch.setattr(cn_hk_market, "fetch_cn_hk_quote_metrics", lambda symbol: {field: "9988.HK", "trailing_pe": 20.0})
    assert peer_service._fetch_single_peer_metrics_from_cn_hk("0700.HK") is None


@pytest.mark.parametrize("marker", [{"success": False}, {"error": "provider failed"}])
def test_cn_hk_peer_metrics_ignore_values_from_failed_payloads(monkeypatch, marker):
    from backend.tools import cn_hk_market
    monkeypatch.setattr(cn_hk_market, "fetch_cn_hk_quote_metrics", lambda symbol: {**marker, "trailing_pe": 20.0})
    assert peer_service._fetch_single_peer_metrics_from_cn_hk("0700.HK") is None


def test_finnhub_peer_cap_falls_back_when_profile_has_no_cap(monkeypatch):
    monkeypatch.setattr(peer_service, "_finnhub_request", lambda path, params:
                        {"name": "Apple"} if path == "stock/profile2" else {"metric": {"marketCapitalization": 100.0}})
    result = peer_service._fetch_single_peer_metrics_from_finnhub("AAPL")
    assert result is not None
    assert result["market_cap"] == 100_000_000.0


@pytest.mark.parametrize("primary, expected", [(0.0, 0.0), ("bad", 20.0), (float("nan"), 20.0)])
def test_finnhub_pe_fallback_preserves_zero_and_recovers_invalid_primary(monkeypatch, primary, expected):
    def request(path, params):
        return {"metric": {"peTTM": primary, "peBasicExclExtraTTM": 20.0,
                           "forwardPE": primary, "peExclExtraAnnual": 20.0}} if path == "stock/metric" else {}
    monkeypatch.setattr(peer_service, "_finnhub_request", request)
    result = peer_service._fetch_single_peer_metrics_from_finnhub("AAPL")
    assert result["trailing_pe"] == expected
    assert result["forward_pe"] == expected


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, "bad", 10 ** 400])
def test_peer_metrics_require_a_usable_number(value):
    assert not peer_service._has_peer_metrics({"market_cap": value})
    assert peer_service._has_peer_metrics({"revenue_growth": 0.0})


def test_finnhub_market_cap_conversion_rejects_overflow():
    assert peer_service._market_cap_to_usd(1e308) is None
    assert peer_service._market_cap_to_usd(100.0) == 100_000_000.0


def test_explicit_peer_inputs_are_normalized_and_poison_entries_skipped(monkeypatch):
    calls = []
    def fetch(symbol):
        calls.append(symbol)
        return {"symbol": symbol, "trailing_pe": 20.0}
    monkeypatch.setattr(peer_service, "_fetch_single_peer_metrics", fetch)
    result = peer_service.fetch_peer_comparison(" aapl ", peers=[None, 42, "", " AAPL ", "msft", " MSFT "])
    assert result is not None
    assert result["subject_symbol"] == "AAPL"
    assert [row["symbol"] for row in result["peers"]] == ["AAPL", "MSFT"]
    assert sorted(calls) == ["AAPL", "MSFT"]


@pytest.mark.parametrize("symbol, limit", [("AAPL", -1), ("AAPL", 0), ("0700.HK", -1), (" ", 3)])
def test_invalid_peer_resolution_requests_do_not_fetch_or_return_defaults(monkeypatch, symbol, limit):
    calls = []
    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=lambda symbol: calls.append(symbol)))
    assert peer_service.resolve_peers(symbol, limit=limit) == []
    assert calls == []


def test_dynamic_peers_are_unique_before_applying_limit(monkeypatch):
    from backend.tools import fmp
    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=lambda symbol: types.SimpleNamespace(info={"industry": "Technology"})))
    monkeypatch.setattr(fmp, "_fmp_request", lambda *args, **kwargs: [
        {"symbol": "msft"}, {"symbol": " MSFT "}, {"symbol": "NVDA"},
    ])
    assert peer_service.resolve_peers("AAPL", limit=2) == ["MSFT", "NVDA"]


def test_resolve_peers_normalizes_target_before_lookup_and_exclusion(monkeypatch):
    seen = []
    def ticker(symbol):
        seen.append(symbol)
        return types.SimpleNamespace(info={})
    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=ticker))
    assert "AAPL" not in peer_service.resolve_peers(" aapl ", limit=4)
    assert seen == ["AAPL"]
    assert "0700.HK" not in peer_service.resolve_peers(" 0700.hk ", limit=4)


def test_sh_peer_market_uses_chinese_defaults(monkeypatch):
    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=lambda symbol: types.SimpleNamespace(info={})))
    assert peer_service._infer_market_from_symbol(" 600519.sh ") == "CN"
    assert all(symbol.endswith((".SS", ".SZ")) for symbol in peer_service.resolve_peers("600519.SH"))


def test_fetch_valuation_uses_finnhub_fallback_when_yfinance_empty(monkeypatch):
    class EmptyTicker:
        def __init__(self, symbol: str):
            self.info = {}

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=EmptyTicker))
    monkeypatch.setattr(
        data_service,
        "_fetch_valuation_from_finnhub",
        lambda symbol: {"market_cap": 123.0, "trailing_pe": 20.0, "forward_pe": 18.0},
    )
    monkeypatch.setattr(
        data_fetchers_equity,
        "_fetch_valuation_from_finnhub",
        lambda symbol: {"market_cap": 123.0, "trailing_pe": 20.0, "forward_pe": 18.0},
    )

    result = data_service.fetch_valuation("AAPL")
    assert isinstance(result, dict)
    assert result["market_cap"] == 123.0
    assert result["trailing_pe"] == 20.0


def test_fetch_financials_uses_finnhub_fallback_when_yfinance_missing(monkeypatch):
    class EmptyTicker:
        def __init__(self, symbol: str):
            self.quarterly_income_stmt = pd.DataFrame()
            self.quarterly_financials = pd.DataFrame()
            self.quarterly_balance_sheet = pd.DataFrame()
            self.quarterly_cashflow = pd.DataFrame()

    fallback_payload = {
        "periods": ["2025FY", "2024FY"],
        "revenue": [100.0, 90.0],
        "gross_profit": [50.0, 45.0],
        "operating_income": [20.0, 18.0],
        "net_income": [15.0, 14.0],
        "eps": [1.2, 1.1],
        "total_assets": [300.0, 280.0],
        "total_liabilities": [120.0, 110.0],
        "operating_cash_flow": [25.0, 24.0],
        "free_cash_flow": [10.0, 9.0],
    }

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=EmptyTicker))
    monkeypatch.setattr(
        data_service,
        "_fetch_financial_statements_from_finnhub",
        lambda symbol, periods=8: fallback_payload,
    )
    monkeypatch.setattr(
        data_fetchers_equity,
        "_fetch_financial_statements_from_finnhub",
        lambda symbol, periods=8: fallback_payload,
    )
    monkeypatch.setattr(
        data_service,
        "_fetch_financial_statements_from_sec_companyfacts",
        lambda symbol, periods=8: None,
    )
    monkeypatch.setattr(
        data_fetchers_equity,
        "_fetch_financial_statements_from_sec_companyfacts",
        lambda symbol, periods=8: None,
    )

    result = data_service.fetch_financial_statements("AAPL")
    assert result == fallback_payload


def test_peer_service_uses_finnhub_when_yfinance_info_empty(monkeypatch):
    class EmptyTicker:
        def __init__(self, symbol: str):
            self.info = {}

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=EmptyTicker))
    monkeypatch.setattr(
        peer_service,
        "_fetch_single_peer_metrics_from_finnhub",
        lambda sym: {
            "symbol": sym,
            "name": sym,
            "trailing_pe": 30.0,
            "forward_pe": 25.0,
            "price_to_book": 5.0,
            "ev_to_ebitda": 12.0,
            "net_margin": 0.2,
            "roe": 0.3,
            "revenue_growth": 0.1,
            "dividend_yield": 0.01,
            "market_cap": 1_000_000_000.0,
        },
    )

    result = peer_service.fetch_peer_comparison("GOOGL", peers=["AAPL", "MSFT"])
    assert isinstance(result, dict)
    rows = result.get("peers") or []
    assert len(rows) == 3
    assert any((row.get("trailing_pe") or 0) > 0 for row in rows)


def test_resolve_peers_falls_back_to_default_list_when_sector_unknown(monkeypatch):
    class EmptyTicker:
        def __init__(self, symbol: str):
            self.info = {}

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=EmptyTicker))
    peers = peer_service.resolve_peers("ZZZZ", limit=4)
    assert len(peers) == 4
    assert all(p != "ZZZZ" for p in peers)


def test_fetch_financials_prefers_sec_companyfacts_before_finnhub(monkeypatch):
    class EmptyTicker:
        def __init__(self, symbol: str):
            self.quarterly_income_stmt = pd.DataFrame()
            self.quarterly_financials = pd.DataFrame()
            self.quarterly_balance_sheet = pd.DataFrame()
            self.quarterly_cashflow = pd.DataFrame()

    sec_payload = {
        "periods": ["2025Q3", "2025Q2"],
        "revenue": [100.0, 90.0],
        "gross_profit": [40.0, 35.0],
        "operating_income": [20.0, 18.0],
        "net_income": [15.0, 14.0],
        "eps": [1.5, 1.4],
        "total_assets": [300.0, 280.0],
        "total_liabilities": [120.0, 110.0],
        "operating_cash_flow": [30.0, 28.0],
        "free_cash_flow": [20.0, 18.0],
    }

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=EmptyTicker))
    monkeypatch.setattr(
        data_service,
        "_fetch_financial_statements_from_sec_companyfacts",
        lambda symbol, periods=8: sec_payload,
    )
    monkeypatch.setattr(
        data_fetchers_equity,
        "_fetch_financial_statements_from_sec_companyfacts",
        lambda symbol, periods=8: sec_payload,
    )
    monkeypatch.setattr(
        data_service,
        "_fetch_financial_statements_from_finnhub",
        lambda symbol, periods=8: None,
    )
    monkeypatch.setattr(
        data_fetchers_equity,
        "_fetch_financial_statements_from_finnhub",
        lambda symbol, periods=8: None,
    )

    result = data_service.fetch_financial_statements("AAPL")
    assert result == sec_payload


def test_fetch_financials_uses_cn_hk_route_for_cn_symbol(monkeypatch):
    payload = {
        "periods": ["2025Q3", "2025Q2"],
        "revenue": [130.0, 110.0],
        "gross_profit": [60.0, 50.0],
        "operating_income": [40.0, 35.0],
        "net_income": [25.0, 22.0],
        "eps": [2.5, 2.2],
        "total_assets": [500.0, 480.0],
        "total_liabilities": [100.0, 95.0],
        "operating_cash_flow": [50.0, 45.0],
        "free_cash_flow": [30.0, 28.0],
    }
    monkeypatch.setattr(
        data_service,
        "_fetch_financial_statements_from_cn_hk_market",
        lambda symbol, periods=8: payload,
    )
    monkeypatch.setattr(
        data_fetchers_equity,
        "_fetch_financial_statements_from_cn_hk_market",
        lambda symbol, periods=8: payload,
    )

    result = data_service.fetch_financial_statements("600519.SS")
    assert result == payload


def test_resolve_peers_uses_market_specific_defaults(monkeypatch):
    class EmptyTicker:
        def __init__(self, symbol: str):
            self.info = {}

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=EmptyTicker))

    cn_peers = peer_service.resolve_peers("600519.SS", limit=3)
    hk_peers = peer_service.resolve_peers("0700.HK", limit=3)
    us_peers = peer_service.resolve_peers("AAPL", limit=3)

    assert cn_peers and all(p.endswith((".SS", ".SZ", ".BJ")) for p in cn_peers)
    assert hk_peers and all(p.endswith(".HK") for p in hk_peers)
    assert us_peers and all("." not in p for p in us_peers)


def test_peer_comparison_shutdown_does_not_wait_for_timed_out_fetches(monkeypatch):
    """R106 回归：as_completed(timeout=8) 只让迭代方抛 FuturesTimeout，
    慢 peer 线程仍在跑；`with ThreadPoolExecutor` 退出时 __exit__ 调
    shutdown(wait=True)，fetch_peer_comparison 会一直阻塞到慢源真正
    返回——注释明写的 8s 全局预算形同虚设（同 R99 fetch_news 缺陷）。
    退出必须 wait=False 并取消排队任务。"""
    import concurrent.futures as cf

    shutdown_calls = []

    class _SpyPool(cf.ThreadPoolExecutor):
        def shutdown(self, wait=True, *, cancel_futures=False):
            shutdown_calls.append({"wait": wait, "cancel_futures": cancel_futures})
            return super().shutdown(wait=wait, cancel_futures=cancel_futures)

    monkeypatch.setattr(peer_service, "ThreadPoolExecutor", _SpyPool)
    monkeypatch.setattr(
        peer_service,
        "_fetch_single_peer_metrics",
        lambda sym: {"symbol": sym, "name": sym, "trailing_pe": 10.0},
    )

    payload = peer_service.fetch_peer_comparison("GOOGL", peers=["AAPL"])

    assert payload is not None
    assert shutdown_calls, "pool 必须被显式关闭"
    assert all(
        call["wait"] is False and call["cancel_futures"] is True
        for call in shutdown_calls
    ), f"shutdown 仍阻塞等待慢源: {shutdown_calls}"


def test_resolve_peers_fmp_screener_skips_poison_items(monkeypatch):
    """R118：FMP stock-screener 返回列表混入毒条目——非 dict 条目的
    item.get AttributeError、symbol 非 str 的 .upper() AttributeError 会落进
    外层 except，让其后的合法 peer 全部丢失（毒条目在首位时整份动态结果
    丢光、静默退回静态兜底）。按条跳过、非 str symbol 丢弃。"""
    class IndustryTicker:
        def __init__(self, symbol):
            self.info = {"industry": "Software—Infrastructure", "sector": "Technology"}

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=IndustryTicker))

    import backend.tools.fmp as fmp_module

    monkeypatch.setattr(
        fmp_module,
        "_fmp_request",
        lambda *args, **kwargs: [
            {"symbol": "MSFT"},
            "poison-entry",
            None,
            {"symbol": None},
            {"symbol": 12345},
            {"symbol": "ORCL"},
            {"symbol": "GOOGL"},  # 自身应被排除
        ],
    )

    peers = peer_service.resolve_peers("GOOGL", limit=6)

    assert "MSFT" in peers
    assert "ORCL" in peers
    assert "GOOGL" not in peers
    assert all(isinstance(p, str) for p in peers)
