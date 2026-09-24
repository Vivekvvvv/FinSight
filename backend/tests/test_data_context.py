import pytest

from backend.orchestration.data_context import DataContextCollector


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, True, False])
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


def test_data_context_mixed_tz_timestamps_do_not_crash():
    """naive 与 aware 的 ISO as_of 混在同一 collector：summarize 里
    max/min(parsed_times) 比较 naive↔aware 抛 TypeError——生产上
    orchestrator.fetch 的 per-source except 会把它当成源失败：已验证
    通过的数据被计 fail、熔断器/健康分被污染。naive 按 UTC 归一
    （与 _parse_datetime / _freshness_hours 同约定）。"""
    collector = DataContextCollector()
    collector.add("news_a", data={"as_of": "2026-01-20T10:00:00Z"})
    collector.add("news_b", data={"as_of": "2026-01-20T12:00:00"})  # naive
    summary = collector.summarize()

    assert summary.as_of_skew_hours == 2.0
    assert summary.as_of == "2026-01-20T12:00:00+00:00"


def test_extract_context_fields_mixed_tz_list_does_not_crash():
    """顶层 list 载荷（聚合 news：各 item 自带 published 格式）混了
    带 Z 与裸 ISO 串——max(candidate_times) 同样 TypeError。"""
    from backend.orchestration.data_context import extract_context_fields

    data = [
        {"as_of": "2026-01-20T10:00:00Z"},
        {"as_of": "2026-01-19T08:00:00"},
    ]
    as_of, _currency, _adjustment = extract_context_fields(data)

    assert as_of == "2026-01-20T10:00:00+00:00"
