import pytest

from backend.orchestration.data_context import DataContextCollector


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1])
def test_data_context_rejects_invalid_skew_limit(value):
    collector = DataContextCollector(max_skew_hours=value)

    assert collector.max_skew_hours == 24.0


def test_data_context_currency_conflict():
    collector = DataContextCollector(max_skew_hours=1)
    collector.add("price", data={"as_of": "2026-01-20T10:00:00Z", "currency": "USD"})
    collector.add("macro", data={"as_of": "2026-01-20T12:30:00Z", "currency": "EUR"})
    summary = collector.summarize()

    assert summary.currency is None
    assert any("currency_conflict" in issue for issue in summary.issues)


def test_data_context_as_of_missing():
    collector = DataContextCollector()
    collector.add("price", data={"currency": "USD"})
    summary = collector.summarize()

    assert any("as_of_missing" in warning for warning in summary.warnings)


def test_data_context_infers_currency_from_ticker():
    collector = DataContextCollector()
    collector.add("price", data={"as_of": "2026-01-20T10:00:00Z"}, ticker="0700.HK")
    summary = collector.summarize()

    assert summary.currency == "HKD"
