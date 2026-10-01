# -*- coding: utf-8 -*-
import time as _time_mod

import backend.tools.tencent_provider as tp
import backend.services.datasource_monitor as dsm


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
