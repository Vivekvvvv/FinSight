# -*- coding: utf-8 -*-
import time as _time_mod

import backend.tools.tencent_provider as tp
import backend.services.datasource_monitor as dsm


def test_tencent_unadjusted_kline_is_used_when_adjusted_series_is_missing(monkeypatch):
    from types import SimpleNamespace
    lines = [["2026-01-05", "100", "101", "102", "99", "10"]]
    monkeypatch.setattr(tp, "_http_get", lambda *a, **kw: SimpleNamespace(
        status_code=200, json=lambda: {"code": 0, "data": {"sh600519": {"day": lines}}}))
    assert tp.fetch_cn_kline("600519.SS")["kline_data"][0]["close"] == 101


def test_tencent_quote_negative_turnover_rate_is_unavailable(monkeypatch):
    monkeypatch.setattr(dsm, "get_monitor", lambda: _FakeMonitor([]))
    parts = _tencent_payload().split('"')[1].split("~")
    parts[52] = "-1"
    monkeypatch.setattr(tp, "_http_get", lambda *a, **kw: _FakeResp('v_sh600519="' + "~".join(parts) + '"'))
    assert tp.fetch_cn_quote("600519.SS")["turnover_rate"] is None


def test_tencent_date_missing_intraday_is_not_labeled_live(monkeypatch):
    from types import SimpleNamespace
    minute = {"data": ["0930 100 10 1000"]}
    monkeypatch.setattr(tp, "_http_get", lambda *a, **kw: SimpleNamespace(
        status_code=200, json=lambda: {"code": 0, "data": {"sh600519": {"data": minute}}}))
    assert tp.fetch_cn_intraday("600519.SS")["freshness_status"] == "unknown"


def test_tencent_intraday_volume_arrays_preserve_zero_and_missing_observations(monkeypatch):
    from types import SimpleNamespace
    lines = ["0930 100 0 0", "0931 101 bad 1000", "0932 102 10 2000"]
    monkeypatch.setattr(tp, "_http_get", lambda *a, **kw: SimpleNamespace(
        status_code=200, json=lambda: {"code": 0, "data": {"sh600519": {"data": {"date": "20260630", "data": lines}}}}))
    result = tp.fetch_cn_intraday("600519.SS")
    assert result["volumes"] == [0.0, None, 1000.0]
    assert len(result["times"]) == len(result["prices"]) == len(result["volumes"])


def test_tencent_intraday_invalid_observation_date_is_unavailable(monkeypatch):
    from types import SimpleNamespace
    for date in ("20260230", "not-a-date", {}):
        minute = {"date": date, "data": ["0930 100 10 1000"]}
        monkeypatch.setattr(tp, "_http_get", lambda *a, **kw: SimpleNamespace(
            status_code=200, json=lambda: {"code": 0, "data": {"sh600519": {"data": minute}}}))
        assert tp.fetch_cn_intraday("600519.SS") is None


def test_tencent_intraday_sorting_preserves_latest_point_and_aligned_arrays(monkeypatch):
    from types import SimpleNamespace
    lines = ["0931 102 20 2000", "0931 103 21 2100", "0930 100 10 1000"]
    monkeypatch.setattr(tp, "_http_get", lambda *a, **kw: SimpleNamespace(
        status_code=200, json=lambda: {"code": 0, "data": {"sh600519": {"data": {"date": "20260630", "data": lines}}}}))
    result = tp.fetch_cn_intraday("600519.SS")
    assert result["times"] == ["09:30", "09:31"]
    assert result["prices"] == [100, 103]
    assert result["volumes"] == [1000, 2100]
    assert result["as_of"] == "2026-06-30T09:31"


def test_tencent_intraday_requires_valid_minute_times(monkeypatch):
    from types import SimpleNamespace
    lines = [f"{time} 100 10 1000" for time in ("9999", "2500", "09aa", "9", "0930")]
    monkeypatch.setattr(tp, "_http_get", lambda *a, **kw: SimpleNamespace(
        status_code=200, json=lambda: {"code": 0, "data": {"sh600519": {"data": {"date": "20260630", "data": lines}}}}))
    assert tp.fetch_cn_intraday("600519.SS")["times"] == ["09:30"]


def test_tencent_intraday_negative_trade_amount_is_unavailable(monkeypatch):
    from types import SimpleNamespace
    lines = ["0930 100 10 -1000"]
    monkeypatch.setattr(tp, "_http_get", lambda *a, **kw: SimpleNamespace(
        status_code=200, json=lambda: {"code": 0, "data": {"sh600519": {"data": {"date": "20260630", "data": lines}}}}))
    result = tp.fetch_cn_intraday("600519.SS")
    assert result["prices"] == [100]
    assert result["intraday_data"][0]["amount"] is None


def test_tencent_intraday_share_volumes_are_finite_nonnegative(monkeypatch):
    from types import SimpleNamespace
    for volume, expected in (("-1", None), ("1e308", None), ("0", 0.0), ("10", 1000.0)):
        lines = [f"0930 100 {volume} 1000"]
        monkeypatch.setattr(tp, "_http_get", lambda *a, **kw: SimpleNamespace(
            status_code=200, json=lambda: {"code": 0, "data": {"sh600519": {"data": {"date": "20260630", "data": lines}}}}))
        assert tp.fetch_cn_intraday("600519.SS")["intraday_data"][0]["volume"] == expected


def test_tencent_intraday_prices_must_be_positive(monkeypatch):
    from types import SimpleNamespace
    lines = ["0930 0 10 1000", "0931 -1 10 1000", "0932 100 10 1000"]
    monkeypatch.setattr(tp, "_http_get", lambda *a, **kw: SimpleNamespace(
        status_code=200, json=lambda: {"code": 0, "data": {"sh600519": {"data": {"date": "20260630", "data": lines}}}}))
    assert tp.fetch_cn_intraday("600519.SS")["prices"] == [100]


def test_tencent_minute_container_identity_must_match_request(monkeypatch):
    from types import SimpleNamespace
    for marker in ({"symbol": "600000.SS"}, {"ticker": "600000.SS"}, {"symbol": {}}):
        minute = {"date": "20260630", "data": ["0930 100 10 1000"], **marker}
        monkeypatch.setattr(tp, "_http_get", lambda *a, **kw: SimpleNamespace(
            status_code=200, json=lambda: {"code": 0, "data": {"sh600519": {"data": minute}}}))
        assert tp.fetch_cn_intraday("600519.SS") is None


def test_tencent_failed_minute_container_cannot_supply_points(monkeypatch):
    from types import SimpleNamespace
    for marker in ({"error": "bad"}, {"success": False}, {"status": " Failed "}):
        minute = {"date": "20260630", "data": ["0930 100 10 1000"], **marker}
        monkeypatch.setattr(tp, "_http_get", lambda *a, **kw: SimpleNamespace(
            status_code=200, json=lambda: {"code": 0, "data": {"sh600519": {"data": minute}}}))
        assert tp.fetch_cn_intraday("600519.SS") is None


def test_tencent_intraday_stock_identity_must_match_request(monkeypatch):
    from types import SimpleNamespace
    for marker in ({"symbol": "600000.SS"}, {"ticker": "600000.SS"}, {"symbol": {}}):
        stock = {"data": {"date": "20260630", "data": ["0930 100 10 1000"]}, **marker}
        monkeypatch.setattr(tp, "_http_get", lambda *a, **kw: SimpleNamespace(
            status_code=200, json=lambda: {"code": 0, "data": {"sh600519": stock}}))
        assert tp.fetch_cn_intraday("600519.SS") is None


def test_tencent_failed_intraday_stock_cannot_supply_points(monkeypatch):
    from types import SimpleNamespace
    for marker in ({"error": "bad"}, {"success": False}, {"status": " Failed "}):
        stock = {"data": {"date": "20260630", "data": ["0930 100 10 1000"]}, **marker}
        monkeypatch.setattr(tp, "_http_get", lambda *a, **kw: SimpleNamespace(
            status_code=200, json=lambda: {"code": 0, "data": {"sh600519": stock}}))
        assert tp.fetch_cn_intraday("600519.SS") is None


def test_tencent_failed_intraday_envelope_cannot_supply_points(monkeypatch):
    from types import SimpleNamespace
    for marker in ({"error": "bad"}, {"success": False}, {"status": " Failed "}):
        payload = {"code": 0, "data": {"sh600519": {"data": {"date": "20260630", "data": ["0930 100 10 1000"]}}}, **marker}
        monkeypatch.setattr(tp, "_http_get", lambda *a, **kw: SimpleNamespace(status_code=200, json=lambda: payload))
        assert tp.fetch_cn_intraday("600519.SS") is None


def test_tencent_kline_order_and_duplicates_preserve_aligned_chart_arrays(monkeypatch):
    from types import SimpleNamespace
    lines = [["2026-01-06", "100", "102", "105", "99", "10"],
             ["2026-01-06", "100", "103", "105", "99", "10"],
             ["2026-01-05", "100", "101", "105", "99", "10"]]
    monkeypatch.setattr(tp, "_http_get", lambda *a, **kw: SimpleNamespace(
        status_code=200, json=lambda: {"code": 0, "data": {"sh600519": {"qfqday": lines}}}))
    result = tp.fetch_cn_kline("600519.SS")
    assert result["dates"] == ["2026-01-05", "2026-01-06"]
    assert [row["close"] for row in result["kline_data"]] == [101, 103]
    assert [row[1] for row in result["values"]] == [101, 103]
    assert result["as_of"] == "2026-01-06"


def test_tencent_kline_date_must_be_a_valid_calendar_observation(monkeypatch):
    from types import SimpleNamespace
    lines = [[day, "100", "101", "102", "99", "10"] for day in ("2026-02-30", "", {}, "2026-01-05")]
    monkeypatch.setattr(tp, "_http_get", lambda *a, **kw: SimpleNamespace(
        status_code=200, json=lambda: {"code": 0, "data": {"sh600519": {"qfqday": lines}}}))
    assert tp.fetch_cn_kline("600519.SS")["dates"] == ["2026-01-05"]


def test_tencent_kline_volume_conversion_is_finite_nonnegative(monkeypatch):
    from types import SimpleNamespace
    for volume, expected in (("-1", None), ("1e308", None), ("0", 0.0), ("10", 1000.0)):
        lines = [["2026-01-05", "100", "101", "102", "99", volume]]
        monkeypatch.setattr(tp, "_http_get", lambda *a, **kw: SimpleNamespace(
            status_code=200, json=lambda: {"code": 0, "data": {"sh600519": {"qfqday": lines}}}))
        assert tp.fetch_cn_kline("600519.SS")["kline_data"][0]["volume"] == expected


def test_tencent_kline_rejects_impossible_high_low_geometry(monkeypatch):
    from types import SimpleNamespace
    for field, invalid in ((1, "103"), (2, "98"), (3, "98"), (4, "103")):
        bad = ["2026-01-04", "100", "101", "102", "99", "10"]
        bad[field] = invalid
        lines = [bad, ["2026-01-05", "100", "101", "102", "99", "10"]]
        monkeypatch.setattr(tp, "_http_get", lambda *a, **kw: SimpleNamespace(
            status_code=200, json=lambda: {"code": 0, "data": {"sh600519": {"qfqday": lines}}}))
        rows = tp.fetch_cn_kline("600519.SS")["kline_data"]
        assert [row["time"] for row in rows] == ["2026-01-05"]


def test_tencent_kline_requires_positive_complete_ohlc_values(monkeypatch):
    from types import SimpleNamespace
    for field, invalid in ((1, "bad"), (2, "0"), (3, "-1"), (4, "")):
        bad = ["2026-01-04", "100", "101", "102", "99", "10"]
        bad[field] = invalid
        lines = [bad, ["2026-01-05", "100", "101", "102", "99", "10"]]
        monkeypatch.setattr(tp, "_http_get", lambda *a, **kw: SimpleNamespace(
            status_code=200, json=lambda: {"code": 0, "data": {"sh600519": {"qfqday": lines}}}))
        rows = tp.fetch_cn_kline("600519.SS")["kline_data"]
        assert [row["time"] for row in rows] == ["2026-01-05"]


def test_tencent_kline_stock_labels_must_match_request(monkeypatch):
    from types import SimpleNamespace
    for marker in ({"symbol": "600000.SS"}, {"ticker": "600000.SS"}, {"symbol": {}}):
        stock = {"qfqday": [["2026-01-05", "100", "101", "102", "99", "10"]], **marker}
        monkeypatch.setattr(tp, "_http_get", lambda *a, **kw: SimpleNamespace(
            status_code=200, json=lambda: {"code": 0, "data": {"sh600519": stock}}))
        assert tp.fetch_cn_kline("600519.SS") is None


def test_failed_tencent_stock_history_cannot_supply_bars(monkeypatch):
    from types import SimpleNamespace
    for marker in ({"error": "bad"}, {"success": False}, {"status": " Failed "}):
        stock = {"qfqday": [["2026-01-05", "100", "101", "102", "99", "10"]], **marker}
        monkeypatch.setattr(tp, "_http_get", lambda *a, **kw: SimpleNamespace(
            status_code=200, json=lambda: {"code": 0, "data": {"sh600519": stock}}))
        assert tp.fetch_cn_kline("600519.SS") is None


def test_failed_tencent_kline_envelopes_cannot_supply_history(monkeypatch):
    from types import SimpleNamespace
    for marker in ({"error": "bad"}, {"success": False}, {"status": " Failed "}):
        payload = {"code": 0, "data": {"sh600519": {"qfqday": [["2026-01-05", "100", "101", "102", "99", "10"]]}}, **marker}
        monkeypatch.setattr(tp, "_http_get", lambda *a, **kw: SimpleNamespace(status_code=200, json=lambda: payload))
        assert tp.fetch_cn_kline("600519.SS") is None


def test_tencent_unsupported_kline_interval_does_not_fetch_daily_bars(monkeypatch):
    from types import SimpleNamespace
    calls = []
    payload = {"code": 0, "data": {"sh600519": {"qfqday": [["2026-01-05", "100", "101", "102", "99", "10"]]}}}
    monkeypatch.setattr(tp, "_http_get", lambda *a, **kw: calls.append(a) or SimpleNamespace(status_code=200, json=lambda: payload))
    for interval in ("1h", "5m", "bad"):
        assert tp.fetch_cn_kline("600519.SS", interval=interval) is None
    assert calls == []


def test_tencent_quote_returns_a_normalized_stock_symbol(monkeypatch):
    monkeypatch.setattr(dsm, "get_monitor", lambda: _FakeMonitor([]))
    monkeypatch.setattr(tp, "_http_get", lambda *a, **kw: _FakeResp(_tencent_payload()))
    assert tp.fetch_cn_quote(" 600519.ss ")["symbol"] == "600519.SS"


def test_tencent_quote_without_observation_evidence_is_not_labeled_live(monkeypatch):
    monkeypatch.setattr(dsm, "get_monitor", lambda: _FakeMonitor([]))
    monkeypatch.setattr(tp, "_http_get", lambda *a, **kw: _FakeResp(_tencent_payload()))
    result = tp.fetch_cn_quote("600519.SS")
    assert result["as_of"] is None
    assert result["freshness_status"] == "unknown"


def test_tencent_split_quote_timestamp_must_be_a_valid_datetime(monkeypatch):
    monkeypatch.setattr(dsm, "get_monitor", lambda: _FakeMonitor([]))
    for day, time in (("20260230", "150000"), ("20260630", "999999"), ("abcdefgh", "150000")):
        parts = _tencent_payload().split('"')[1].split("~")
        parts[30], parts[31] = day, time
        monkeypatch.setattr(tp, "_http_get", lambda *a, **kw: _FakeResp('v_sh600519="' + "~".join(parts) + '"'))
        assert tp.fetch_cn_quote("600519.SS")["as_of"] is None


def test_tencent_quote_uses_the_compact_provider_timestamp(monkeypatch):
    monkeypatch.setattr(dsm, "get_monitor", lambda: _FakeMonitor([]))
    parts = _tencent_payload().split('"')[1].split("~")
    parts[30], parts[31] = "20260630161413", "-9.47"
    monkeypatch.setattr(tp, "_http_get", lambda *a, **kw: _FakeResp('v_sh600519="' + "~".join(parts) + '"'))
    assert tp.fetch_cn_quote("600519.SS")["as_of"] == "2026-06-30T16:14:13+08:00"


def test_tencent_quote_does_not_invent_observation_time(monkeypatch):
    monkeypatch.setattr(dsm, "get_monitor", lambda: _FakeMonitor([]))
    monkeypatch.setattr(tp, "_http_get", lambda *a, **kw: _FakeResp(_tencent_payload()))
    assert tp.fetch_cn_quote("600519.SS")["as_of"] is None


def test_tencent_circulating_market_cap_requires_finite_positive_values(monkeypatch):
    monkeypatch.setattr(dsm, "get_monitor", lambda: _FakeMonitor([]))
    for cap in ("0", "-1", "1e308"):
        parts = _tencent_payload().split('"')[1].split("~")
        parts[44] = cap
        monkeypatch.setattr(tp, "_http_get", lambda *a, **kw: _FakeResp('v_sh600519="' + "~".join(parts) + '"'))
        assert tp.fetch_cn_quote("600519.SS")["circulating_cap"] is None


def test_tencent_total_market_cap_requires_finite_positive_values(monkeypatch):
    monkeypatch.setattr(dsm, "get_monitor", lambda: _FakeMonitor([]))
    for cap in ("0", "-1", "1e308"):
        parts = _tencent_payload().split('"')[1].split("~")
        parts[45] = cap
        monkeypatch.setattr(tp, "_http_get", lambda *a, **kw: _FakeResp('v_sh600519="' + "~".join(parts) + '"'))
        assert tp.fetch_cn_quote("600519.SS")["market_cap"] is None


def test_tencent_quote_volume_conversion_requires_finite_nonnegative_values(monkeypatch):
    monkeypatch.setattr(dsm, "get_monitor", lambda: _FakeMonitor([]))
    for volume, expected in (("-10", None), ("1e308", None), ("0", 0.0), ("10", 1000.0)):
        raw = _tencent_payload().replace("~12345~", f"~{volume}~")
        monkeypatch.setattr(tp, "_http_get", lambda *a, **kw: _FakeResp(raw))
        assert tp.fetch_cn_quote("600519.SS")["volume"] == expected


def test_tencent_percentage_overflow_does_not_leak_infinite_json(monkeypatch):
    import json
    monkeypatch.setattr(dsm, "get_monitor", lambda: _FakeMonitor([]))
    raw = _tencent_payload().replace("~2080.00~", "~1e-320~")
    monkeypatch.setattr(tp, "_http_get", lambda *a, **kw: _FakeResp(raw))
    result = tp.fetch_cn_quote("600519.SS")
    assert result["price"] == 2086
    assert result["change_percent"] is None
    json.dumps(result, allow_nan=False)


def test_tencent_quote_requires_positive_price_and_previous_close(monkeypatch):
    monkeypatch.setattr(dsm, "get_monitor", lambda: _FakeMonitor([]))
    for old, new in (("~2086.00~", "~0~"), ("~2086.00~", "~-1~"), ("~2080.00~", "~-1~")):
        monkeypatch.setattr(tp, "_http_get", lambda *a, **kw: _FakeResp(_tencent_payload().replace(old, new)))
        assert tp.fetch_cn_quote("600519.SS") is None


def test_tencent_quote_requires_matching_internal_stock_code(monkeypatch):
    monkeypatch.setattr(dsm, "get_monitor", lambda: _FakeMonitor([]))
    raw = _tencent_payload().replace("~600519~", "~600000~")
    monkeypatch.setattr(tp, "_http_get", lambda *a, **kw: _FakeResp(raw))
    assert tp.fetch_cn_quote("600519.SS") is None


def test_tencent_quote_requires_matching_response_label(monkeypatch):
    monkeypatch.setattr(dsm, "get_monitor", lambda: _FakeMonitor([]))
    raw = _tencent_payload().replace("v_sh600519", "v_sh600000")
    monkeypatch.setattr(tp, "_http_get", lambda *a, **kw: _FakeResp(raw))
    assert tp.fetch_cn_quote("600519.SS") is None


class _FakeResp:
    status_code = 200

    def __init__(self, text: str):
        self.text = text


def _tencent_payload() -> str:
    # v_sh600519="51~贵州茅台~600519~2086.00~2080.00~...~52字段"
    parts = ["51", "贵州茅台", "600519", "2086.00", "2080.00", "2085.00", "12345"]
    parts += ["0"] * (53 - len(parts))
    return 'v_sh600519="' + "~".join(parts) + '"'


class _FakeMonitor:
    def __init__(self, recorded: list):
        self._recorded = recorded

    def record_success(self, source, response_time_ms=0.0):
        self._recorded.append((source, response_time_ms))

    def record_failure(self, source, reason):
        pass


def test_cn_quote_response_time_survives_wall_clock_jump(monkeypatch):
    """fetch_cn_quote 的 start_time 用 time.time()（墙钟）锚定：上游响应
    途中系统时钟后跳（w32time 回校/NTP 回拨/VM 恢复快照）把
    (now-start) 拉成负值——负 response_time_ms 传给
    datasource_monitor.record_success 被其 >0 门槛静默丢弃（成功调用
    无计时样本）；前跳则一次请求灌入数小时级样本，avg_response_time_ms
    被一条污染数据支配到滚出 100 样本窗口。时延是区间计时，必须用单调钟
    （同 58464b1/35553af/beff9ef/923aa76/a2edc69/8835dfb 修复类）。"""
    wall = {"t": 1_700_000_000.0}
    mono = {"t": 1_000.0}
    monkeypatch.setattr(_time_mod, "time", lambda: wall["t"])
    monkeypatch.setattr(_time_mod, "monotonic", lambda: mono["t"])

    recorded = []
    monkeypatch.setattr(dsm, "get_monitor", lambda: _FakeMonitor(recorded))

    def _fake_http_get(url, **_kwargs):
        # 上游往返期间墙钟后跳 1h——真实耗时 0.3s
        wall["t"] -= 3600.0
        mono["t"] += 0.3
        return _FakeResp(_tencent_payload())

    monkeypatch.setattr(tp, "_http_get", _fake_http_get)

    payload = tp.fetch_cn_quote("600519.SS")

    assert payload is not None
    assert payload["source"] == "tencent"
    assert recorded, "成功路径必须上报时延"
    source, ms = recorded[0]
    assert source == "tencent"
    assert 0 <= ms <= 60_000, f"时延观测必须反映真实耗时而非墙钟跳变: {ms}"
