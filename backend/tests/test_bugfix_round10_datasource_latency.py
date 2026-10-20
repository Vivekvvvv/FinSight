# -*- coding: utf-8 -*-
"""零请求数据源的响应时间不能落地成 0.0 ms。

`get_health_report()` 已经为 success_rate 加了零请求守卫（0.0% 会被读成
"全部失败"），但同一份报告里 avg_response_time_ms 仍照报 0.0——那会被读成
"0 毫秒响应"，是"最快"，而事实是这个源根本没被调用过（项目规则 2）。
"""
from __future__ import annotations


def test_health_report_reports_no_latency_for_never_used_sources():
    """零请求源不报 0.0 ms——那是没测过，不是测得最快。"""
    from backend.services.datasource_monitor import DataSourceMonitor

    mon = DataSourceMonitor()
    for _ in range(5):
        mon.record_success("tencent", 120.0)

    sources = mon.get_health_report()["sources"]

    assert sources["yahoo"]["total_requests"] == 0
    assert sources["yahoo"]["avg_response_time_ms"] is None
    # 有流量的源照旧报数字（不能把守卫扩散成"永远 None"）
    assert sources["tencent"]["avg_response_time_ms"] == 120.0


def test_never_used_source_latency_matches_success_rate_availability():
    """同一份报告里两个"没测过"的指标必须同形缺省，不能一个 None 一个 0.0。"""
    from backend.services.datasource_monitor import DataSourceMonitor

    sources = DataSourceMonitor().get_health_report()["sources"]

    for name, metrics in sources.items():
        if metrics["total_requests"] == 0:
            assert metrics["success_rate"] is None, name
            assert metrics["avg_response_time_ms"] is None, name
