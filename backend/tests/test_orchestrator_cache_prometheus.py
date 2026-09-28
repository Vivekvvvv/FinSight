# -*- coding: utf-8 -*-
"""fetch 的缓存命中/未命中必须同步进 Prometheus——
monitoring/rules/alerts.yml 的 LowCacheHitRate 全靠
finsight_cache_hit_rate gauge，此前没有任何调用方喂数。
force_refresh（health_probe 周期任务）是绕缓存不是真 miss，
不得计入，否则持续拉低命中率造成误报。"""
from __future__ import annotations

import pytest


@pytest.fixture()
def orchestrator():
    from backend.orchestration.orchestrator import ToolOrchestrator

    return ToolOrchestrator()


def _sample(name: str, prefix: str) -> float | None:
    from backend.monitoring.prometheus_exporter import registry

    return registry.get_sample_value(name, {"cache_key_prefix": prefix})


def test_cache_hit_exports_hit_rate(orchestrator):
    orchestrator.cache.set("t_hit:AAA", {"close": 1.0})
    res = orchestrator.fetch("t_hit", "AAA")

    assert res.success and res.cached
    assert _sample("finsight_cache_hits_total", "t_hit") == 1.0
    assert _sample("finsight_cache_hit_rate", "t_hit") == 100.0


def test_cache_miss_exports_hit_rate_zero(orchestrator):
    res = orchestrator.fetch("t_miss", "BBB")

    assert not res.success  # tools_module 缺失的兜底失败
    assert _sample("finsight_cache_misses_total", "t_miss") == 1.0
    assert _sample("finsight_cache_hit_rate", "t_miss") == 0.0


def test_hit_then_miss_computes_ratio(orchestrator):
    orchestrator.cache.set("t_ratio:AAA", {"close": 1.0})
    orchestrator.fetch("t_ratio", "AAA")   # hit
    orchestrator.fetch("t_ratio", "BBB")   # miss

    # 比率来自进程级 _stats 累计，与单次无关
    assert _sample("finsight_cache_hit_rate", "t_ratio") == 50.0


def test_force_refresh_does_not_count_as_miss(orchestrator):
    """health_probe 周期任务走 force_refresh 绕缓存——计入 miss 会
    持续把命中率拉低，LowCacheHitRate 误报。"""
    orchestrator.cache.set("t_ff:AAA", {"close": 1.0})
    orchestrator.fetch("t_ff", "AAA", force_refresh=True)

    assert orchestrator._stats["cache_misses"] == 0
    assert orchestrator._stats["cache_hits"] == 0
    # 该前缀未导出任何序列
    assert _sample("finsight_cache_hit_rate", "t_ff") is None
    assert _sample("finsight_cache_misses_total", "t_ff") is None


def test_no_sources_miss_path_counts_once(orchestrator):
    """'if not sources' 分支也是 miss——只计一次（不进源迭代分支）。"""
    orchestrator.fetch("t_nosrc", "CCC")

    assert orchestrator._stats["cache_misses"] == 1
    assert _sample("finsight_cache_misses_total", "t_nosrc") == 1.0


def test_export_failure_does_not_break_fetch(orchestrator, monkeypatch):
    """exporter 挂掉只能丢指标，不能把取数链路弄炸。"""
    import backend.orchestration.orchestrator as module

    class _Boom:
        def __getattr__(self, name):
            def _raise(*a, **k):
                raise RuntimeError("exporter down")
            return _raise

    monkeypatch.setattr(module, "_prometheus_module", _Boom())

    res = orchestrator.fetch("t_boom", "DDD")
    assert not res.success  # 正常走到兜底失败，而非 exporter 异常
    assert orchestrator._stats["cache_misses"] == 1
