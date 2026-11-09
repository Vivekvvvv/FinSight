from __future__ import annotations

import pytest

from backend.tools import fmp


@pytest.mark.parametrize("bad_profile", [{"success": False}, {"error": "bad"}, {"status": " Failed "},
                                      {"symbol": "MSFT"}, {"ticker": "MSFT"}])
def test_fmp_profile_selects_valid_matching_company_after_invalid_rows(monkeypatch, bad_profile):
    valid = {"symbol": " aapl ", "companyName": "Apple"}
    monkeypatch.setattr(fmp, "_fmp_request", lambda *args, **kwargs: [
        {"symbol": "AAPL", "companyName": "Wrong", **bad_profile}, valid])
    assert fmp.get_company_profile("AAPL") == valid


@pytest.mark.parametrize("field", ["sharesNumber", "marketValue"])
@pytest.mark.parametrize("value", [True, {}, "bad", float("inf"), "12.5"])
def test_fmp_holding_quantities_are_finite_numeric_values(monkeypatch, field, value):
    row = {"asset": "AAPL", "sharesNumber": 10, "marketValue": 100, field: value}
    monkeypatch.setattr(fmp, "_fmp_request", lambda *args, **kwargs: [row])
    result = fmp.get_etf_holdings("SPY")[0]
    output_field = "shares" if field == "sharesNumber" else "value"
    assert result[output_field] == (12.5 if value == "12.5" else 0)
    assert not isinstance(result[output_field], bool)


@pytest.mark.parametrize("kind", ["sectors", "holdings"])
@pytest.mark.parametrize("weight", ["101%", "-10%", 101, -1])
def test_fmp_weights_cannot_publish_impossible_percentages(monkeypatch, kind, weight):
    rows = [{"sector": "Bad", "asset": "BAD", "weightPercentage": weight},
            {"sector": "Technology", "asset": "AAPL", "weightPercentage": "10%"}]
    monkeypatch.setattr(fmp, "_fmp_request", lambda *args, **kwargs: rows)
    if kind == "sectors":
        assert fmp.get_etf_sector_weights("SPY") == [{"sector": "Technology", "weight": 10}]
    else:
        assert [row["weight"] for row in fmp.get_etf_holdings("SPY")] == [10, 0]


@pytest.mark.parametrize("limit", [0, -1])
def test_nonpositive_fmp_holdings_and_constituent_limits_stop_before_external_io(monkeypatch, limit):
    calls = []
    monkeypatch.setattr(fmp, "_fmp_request", lambda *args, **kwargs: calls.append(args) or [])
    assert fmp.get_etf_holdings("SPY", limit=limit) == []
    assert fmp.get_index_constituents("^GSPC", limit=limit) == []
    assert calls == []


@pytest.mark.parametrize("sector", [True, 123, {}, [], "  "])
def test_fmp_sector_names_cannot_publish_nontext_exposure_labels(monkeypatch, sector):
    rows = [{"sector": sector, "weightPercentage": "40%"},
            {"sector": " Technology ", "weightPercentage": "60%"}]
    monkeypatch.setattr(fmp, "_fmp_request", lambda *args, **kwargs: rows)
    assert fmp.get_etf_sector_weights("SPY") == [{"sector": "Technology", "weight": 60}]


@pytest.mark.parametrize("kind", ["product", "geographic"])
def test_fmp_segmentation_names_require_nonempty_normalized_text(monkeypatch, kind):
    monkeypatch.setattr(fmp, "_fmp_request", lambda *args, **kwargs: [{"AAPL": {
        " Cloud ": 100, "  ": 50, 123: 50}}])
    fetch = fmp.get_revenue_product_segmentation if kind == "product" else fmp.get_revenue_geographic_segmentation
    result = fetch("AAPL")
    assert result == [{"segment" if kind == "product" else "region": "Cloud", "revenue": 100, "percentage": 100}]


@pytest.mark.parametrize("kind", ["product", "geographic"])
def test_fmp_segmentation_total_overflow_cannot_publish_fabricated_zero_shares(monkeypatch, kind):
    monkeypatch.setattr(fmp, "_fmp_request", lambda *args, **kwargs: [{"AAPL": {"One": 1e308, "Two": 1e308}}])
    fetch = fmp.get_revenue_product_segmentation if kind == "product" else fmp.get_revenue_geographic_segmentation
    assert fetch("AAPL") == []


@pytest.mark.parametrize("kind", ["product", "geographic"])
def test_fmp_segmentation_uses_latest_dated_matching_company_row(monkeypatch, kind):
    rows = [{"date": "2023-12-31", "AAPL": {"Old": 50}},
            {"date": "2025-12-31", "MSFT": {"Other": 1000}},
            {"date": "2024-12-31", " aapl ": {"Latest": 100}}]
    monkeypatch.setattr(fmp, "_fmp_request", lambda *args, **kwargs: rows)
    fetch = fmp.get_revenue_product_segmentation if kind == "product" else fmp.get_revenue_geographic_segmentation
    result = fetch("AAPL")
    assert [row["segment" if kind == "product" else "region"] for row in result] == ["Latest"]


@pytest.mark.parametrize("kind", ["product", "geographic"])
@pytest.mark.parametrize("failure", [{"error": "bad"}, {"success": False}, {"status": " Failed "}])
def test_failed_segmentation_rows_cannot_supply_revenue(monkeypatch, kind, failure):
    fetch = fmp.get_revenue_product_segmentation if kind == "product" else fmp.get_revenue_geographic_segmentation
    failed = {"AAPL": {"Bad": 900}, **failure}
    monkeypatch.setattr(fmp, "_fmp_request", lambda *args, **kwargs: [failed])
    assert fetch("AAPL") == []
    monkeypatch.setattr(fmp, "_fmp_request", lambda *args, **kwargs: [failed, {"AAPL": {"Valid": 100}}])
    assert [row["revenue"] for row in fetch("AAPL")] == [100]


@pytest.mark.parametrize("kind", ["product", "geographic"])
def test_fmp_segmentation_never_substitutes_another_companys_revenue(monkeypatch, kind):
    fetch = fmp.get_revenue_product_segmentation if kind == "product" else fmp.get_revenue_geographic_segmentation
    monkeypatch.setattr(fmp, "_fmp_request", lambda *args, **kwargs: [{"MSFT": {"Foreign": 900}}])
    assert fetch("AAPL") == []
    monkeypatch.setattr(fmp, "_fmp_request", lambda *args, **kwargs: [
        {"MSFT": {"Foreign": 900}}, {" aapl ": {"Actual": 100}}])
    result = fetch("AAPL")
    assert len(result) == 1
    assert result[0]["revenue"] == 100
    assert result[0]["segment" if kind == "product" else "region"] == "Actual"


@pytest.mark.parametrize("ticker", [True, 123, [], {}, "  "])
@pytest.mark.parametrize("kind", ["holdings", "constituents"])
def test_nontext_fmp_instrument_rows_do_not_break_valid_results(monkeypatch, ticker, kind):
    rows = [{"asset": ticker, "symbol": ticker, "weightPercentage": "10"},
            {"asset": " aapl ", "symbol": " aapl ", "weightPercentage": "5"}]
    monkeypatch.setattr(fmp, "_fmp_request", lambda *args, **kwargs: rows)
    result = fmp.get_etf_holdings("SPY") if kind == "holdings" else fmp.get_index_constituents("^GSPC")
    assert [row["symbol"] for row in result] == ["AAPL"]


@pytest.mark.parametrize("kind", ["sectors", "holdings", "constituents"])
@pytest.mark.parametrize("failure", [{"error": "failed"}, {"success": False}, {"status": " Unavailable "}])
def test_failed_fmp_rows_cannot_lose_markers_and_become_valid_exposures(monkeypatch, kind, failure):
    rows = [{"sector": "Tech", "asset": "AAPL", "symbol": "AAPL", "weightPercentage": "10%"},
            {"sector": "Bad", "asset": "BAD", "symbol": "BAD", "weightPercentage": "90%", **failure}]
    monkeypatch.setattr(fmp, "_fmp_request", lambda *args, **kwargs: rows)
    if kind == "sectors":
        result = fmp.get_etf_sector_weights("SPY")
        assert [row["sector"] for row in result] == ["Tech"]
    elif kind == "holdings":
        result = fmp.get_etf_holdings("SPY")
        assert [row["symbol"] for row in result] == ["AAPL"]
    else:
        result = fmp.get_index_constituents("^GSPC")
        assert [row["symbol"] for row in result] == ["AAPL"]
