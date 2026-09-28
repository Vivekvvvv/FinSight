# -*- coding: utf-8 -*-
"""record_success/record_failure 必须把指标同步进 Prometheus gauge——
monitoring/rules/alerts.yml 里 DataSourceDegraded / DataSourceDown /
LowDataSourceSuccessRate / SlowDataSourceResponse 四条告警全靠这三个序列。
此前 update_data_source_health 零调用方，gauge 永远缺序列，告警形同虚设。"""
from __future__ import annotations

import pytest


@pytest.fixture()
def monitor():
    from backend.services.datasource_monitor import DataSourceMonitor

    return DataSourceMonitor()


def _sample(name: str, source: str) -> float | None:
    from backend.monitoring.prometheus_exporter import registry

    return registry.get_sample_value(name, {"source_name": source})


def test_record_success_exports_health_gauges(monitor):
    monitor.record_success("tencent", 250.0)

    # exporter 文档化刻度：0=down, 1=degraded, 2=healthy
    assert _sample("finsight_data_source_health_status", "tencent") == 2
    # 0-100 刻度，对齐 alerts.yml 的 <80 阈值
    assert _sample("finsight_data_source_success_rate", "tencent") == 100.0
    assert _sample("finsight_data_source_response_time_ms", "tencent") == 250.0


def test_first_failure_exports_down_status(monitor):
    monitor.record_failure("yahoo", "timeout")

    # 首败后 success_rate=0 → status=critical → 0（DataSourceDown 告警源）
    assert _sample("finsight_data_source_health_status", "yahoo") == 0
    assert _sample("finsight_data_source_success_rate", "yahoo") == 0.0


def test_consecutive_failures_export_degraded_status(monitor):
    for _ in range(3):
        monitor.record_failure("demo", "timeout")

    # 连续失败 ≥3 → status=degraded → 1（DataSourceDegraded 告警源）
    assert _sample("finsight_data_source_health_status", "demo") == 1


def test_recovery_exports_healthy_status(monitor):
    for _ in range(3):
        monitor.record_failure("tencent", "timeout")
    for _ in range(10):
        monitor.record_success("tencent", 100.0)

    assert _sample("finsight_data_source_health_status", "tencent") == 2


def test_zero_traffic_source_exports_no_series(monitor):
    """零流量源不得落盘 gauge——否则 success_rate=0/health=0 会被
    DataSourceDown 当成"完全不可用"误报。"""
    monitor.record_success("tencent", 100.0)

    # "unknown" 在 _metrics 里存在但全代码库无人记录它
    assert _sample("finsight_data_source_health_status", "unknown") is None
    assert _sample("finsight_data_source_success_rate", "unknown") is None


def test_unregistered_source_is_noop(monitor):
    """不在 _metrics 里的源早退，不导出、不抛异常。"""
    monitor.record_success("nonexistent", 1.0)  # type: ignore[arg-type]

    assert _sample("finsight_data_source_health_status", "nonexistent") is None


def test_export_failure_does_not_break_recording(monitor, monkeypatch):
    """exporter 挂了只能丢指标，不能把数据通路的 record_* 弄炸。"""
    import backend.services.datasource_monitor as module

    def _boom(*args):
        raise RuntimeError("exporter down")

    monkeypatch.setattr(module, "_prometheus_update", _boom)

    monitor.record_success("tencent", 1.0)
    assert monitor._metrics["tencent"].total_requests == 1
