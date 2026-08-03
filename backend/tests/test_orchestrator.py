# -*- coding: utf-8 -*-
"""
Step 1.3 测试 - ToolOrchestrator 单元测试
验证多源回退和缓存集成
"""

import sys
import os
import time
import logging
from types import SimpleNamespace

import pytest

# 添加项目根目录到路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from backend.orchestration import ToolOrchestrator, DataSource, FetchResult, DataCache


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "2"])
def test_orchestrator_rejects_invalid_health_fail_rate(monkeypatch, value):
    monkeypatch.setenv("PRICE_HEALTH_FAIL_RATE", value)

    orchestrator = ToolOrchestrator(tools_module=SimpleNamespace())

    assert orchestrator.health_fail_rate_threshold == 0.6


def test_orchestrator_invalid_positive_integer_config_uses_defaults(monkeypatch):
    for name in (
        "CB_FAILURE_THRESHOLD",
        "CB_RECOVERY_TIMEOUT",
        "CB_HALF_OPEN_SUCCESS",
        "PRICE_HEALTH_LATENCY_MS",
        "PRICE_HEALTH_MIN_CALLS",
        "PRICE_HEALTH_SKIP_SECONDS",
    ):
        monkeypatch.setenv(name, "invalid")

    orchestrator = ToolOrchestrator(tools_module=SimpleNamespace())

    assert orchestrator.circuit_breaker.failure_threshold == 3
    assert orchestrator.circuit_breaker.recovery_timeout == 120
    assert orchestrator.circuit_breaker.half_open_success_threshold == 1
    assert orchestrator.health_latency_threshold_ms == 5000
    assert orchestrator.health_min_calls == 3
    assert orchestrator.health_skip_seconds == 300


# ============================================
# Mock 数据源函数（用于测试）
# ============================================

def mock_source_success(ticker: str) -> str:
    """总是成功的模拟数据源"""
    return f"{ticker} Current Price: $150.00 | Change: $2.50 (+1.69%)"


def mock_source_fail(ticker: str) -> str:
    """总是失败的模拟数据源"""
    raise Exception("Mock source failed")


def mock_source_rate_limited(ticker: str) -> str:
    """返回限速错误的模拟数据源"""
    return "Error: Too Many Requests. Rate limited."


def mock_source_none(ticker: str) -> None:
    """返回 None 的模拟数据源"""
    return None


def mock_source_slow(ticker: str) -> str:
    """慢速数据源"""
    time.sleep(0.5)
    return f"{ticker} Current Price: $100.00 | Change: $1.00 (+1.00%)"


# ============================================
# 测试用例
# ============================================

def test_orchestrator_init():
    """测试编排器初始化"""
    orchestrator = ToolOrchestrator()
    
    assert orchestrator is not None
    assert orchestrator.cache is not None
    assert orchestrator.validator is not None
    assert len(orchestrator.sources) == 0  # 未加载工具模块时为空
    
    print("[OK] 编排器初始化测试通过")


def test_manual_source_registration():
    """测试手动注册数据源"""
    orchestrator = ToolOrchestrator()
    
    # 手动添加数据源
    orchestrator.sources['price'] = [
        DataSource('mock_success', mock_source_success, 1, 60),
        DataSource('mock_fail', mock_source_fail, 2, 60),
    ]
    
    assert len(orchestrator.sources['price']) == 2
    assert orchestrator.sources['price'][0].name == 'mock_success'
    
    print("[OK] 手动注册数据源测试通过")


def test_fetch_success():
    """测试成功获取数据"""
    orchestrator = ToolOrchestrator()
    orchestrator.sources['price'] = [
        DataSource('mock_success', mock_source_success, 1, 60),
    ]
    
    result = orchestrator.fetch('price', 'AAPL')
    
    assert result.success == True, f"应该成功，但得到: {result.error}"
    assert result.source == 'mock_success'
    assert result.cached == False
    assert 'AAPL' in result.data
    assert result.duration_ms > 0
    
    print("[OK] 成功获取数据测试通过")


def test_fetch_with_fallback():
    """测试失败后回退到备用数据源"""
    orchestrator = ToolOrchestrator()
    orchestrator.sources['price'] = [
        DataSource('mock_fail', mock_source_fail, 1, 60),      # 优先级高但会失败
        DataSource('mock_success', mock_source_success, 2, 60), # 备用
    ]
    
    result = orchestrator.fetch('price', 'AAPL')
    
    assert result.success == True
    assert result.source == 'mock_success', "应该回退到 mock_success"
    
    stats = orchestrator.get_stats()
    assert stats['orchestrator']['fallback_used'] == 1, "应该记录一次回退"
    
    print("[OK] 失败回退测试通过")


def test_fetch_all_fail():
    """测试所有数据源都失败"""
    orchestrator = ToolOrchestrator()
    orchestrator.sources['price'] = [
        DataSource('mock_fail1', mock_source_fail, 1, 60),
        DataSource('mock_fail2', mock_source_fail, 2, 60),
    ]
    
    result = orchestrator.fetch('price', 'AAPL')
    
    assert result.success == False
    assert result.error is not None
    assert 'tried:' in result.source
    
    print("[OK] 所有数据源失败测试通过")


def test_multi_source_error_is_redacted_from_result_trace_events_and_logs(monkeypatch, caplog):
    import backend.orchestration.orchestrator as orchestrator_module

    sentinel = "PRIVATE_SOURCE_API_TOKEN"
    emitted = []

    class _TraceEmitter:
        def emit_cache_miss(self, *_args, **_kwargs):
            pass

        def emit_data_source_query(self, *args, **kwargs):
            emitted.append((args, kwargs))

    def _fail(_ticker):
        raise RuntimeError(sentinel)

    monkeypatch.setattr(orchestrator_module, "get_trace_emitter", lambda: _TraceEmitter())
    caplog.set_level(logging.INFO, logger=orchestrator_module.__name__)
    orchestrator = ToolOrchestrator()
    orchestrator.sources['price'] = [DataSource('private_source', _fail, 1, 60)]

    result = orchestrator.fetch('price', 'AAPL', force_refresh=True)

    serialized = str({"result": result.to_dict(), "emitted": emitted})
    assert result.error == "All data sources failed: RuntimeError"
    assert result.trace['error'] == 'RuntimeError'
    assert sentinel not in serialized
    assert sentinel not in caplog.text
    assert "RuntimeError" in serialized


def test_direct_tool_error_is_redacted_from_result_and_trace():
    sentinel = "PRIVATE postgres://orchestrator:secret@db/data"

    class _FailingTools:
        @staticmethod
        def get_company_news(_ticker):
            raise RuntimeError(sentinel)

    orchestrator = ToolOrchestrator(tools_module=_FailingTools())

    result = orchestrator.fetch('news', 'AAPL')

    assert result.success is False
    assert result.error == 'direct_tool_error'
    assert result.trace['error'] == 'direct_tool_error'
    assert sentinel not in str(result.to_dict())


def test_cache_integration():
    """测试缓存集成"""
    orchestrator = ToolOrchestrator()
    call_count = [0]  # 使用列表来在闭包中修改
    
    def counting_source(ticker: str) -> str:
        call_count[0] += 1
        return f"{ticker} Price: $100.00"
    
    orchestrator.sources['price'] = [
        DataSource('counting', counting_source, 1, 60),
    ]
    
    # 第一次调用 - 应该调用数据源
    result1 = orchestrator.fetch('price', 'AAPL')
    assert result1.success == True
    assert result1.cached == False
    assert call_count[0] == 1
    
    # 第二次调用 - 应该使用缓存
    result2 = orchestrator.fetch('price', 'AAPL')
    assert result2.success == True
    assert result2.cached == True
    assert call_count[0] == 1, "应该使用缓存，不再调用数据源"
    
    # 强制刷新 - 应该再次调用数据源
    result3 = orchestrator.fetch('price', 'AAPL', force_refresh=True)
    assert result3.cached == False
    assert call_count[0] == 2
    
    print("[OK] 缓存集成测试通过")


def test_rate_limit_handling():
    """测试限速处理"""
    orchestrator = ToolOrchestrator()
    orchestrator.sources['price'] = [
        DataSource('rate_limited', mock_source_rate_limited, 1, 60),
        DataSource('mock_success', mock_source_success, 2, 60),
    ]
    
    result = orchestrator.fetch('price', 'AAPL')
    
    assert result.success == True
    assert result.source == 'mock_success', "应该回退到成功的数据源"
    
    print("[OK] 限速处理测试通过")


def test_none_result_handling():
    """测试 None 结果处理"""
    orchestrator = ToolOrchestrator()
    orchestrator.sources['price'] = [
        DataSource('returns_none', mock_source_none, 1, 60),
        DataSource('mock_success', mock_source_success, 2, 60),
    ]
    
    result = orchestrator.fetch('price', 'AAPL')
    
    assert result.success == True
    assert result.source == 'mock_success', "应该跳过返回 None 的数据源"
    
    print("[OK] None 结果处理测试通过")


def test_consecutive_failures_priority():
    """测试连续失败后优先级降低"""
    orchestrator = ToolOrchestrator()
    
    fail_source = DataSource('often_fails', mock_source_fail, 1, 60)
    fail_source.consecutive_failures = 5  # 已经失败多次
    
    success_source = DataSource('reliable', mock_source_success, 2, 60)
    
    orchestrator.sources['price'] = [fail_source, success_source]
    
    result = orchestrator.fetch('price', 'AAPL')
    
    # 由于 fail_source 有很多连续失败，应该先尝试 success_source
    assert result.success == True
    assert result.source == 'reliable'
    
    print("[OK] 连续失败优先级降低测试通过")


def test_stats_tracking():
    """测试统计追踪"""
    orchestrator = ToolOrchestrator()
    orchestrator.sources['price'] = [
        DataSource('mock_success', mock_source_success, 1, 60),
    ]
    
    # 初始统计
    stats = orchestrator.get_stats()
    assert stats['orchestrator']['total_requests'] == 0
    
    # 执行一些请求
    orchestrator.fetch('price', 'AAPL')
    orchestrator.fetch('price', 'AAPL')  # 缓存命中
    orchestrator.fetch('price', 'GOOGL')
    
    stats = orchestrator.get_stats()
    assert stats['orchestrator']['total_requests'] == 3
    assert stats['orchestrator']['cache_hits'] == 1
    
    # 检查缓存统计
    assert stats['cache']['hits'] >= 1
    
    print("[OK] 统计追踪测试通过")


def test_negative_cache_hit_returns_failure_not_success():
    """负缓存命中必须判失败（R2 回归）：不能把 {"error":...} 载荷当成功数据返回，
    否则下游把错误 dict 渲染成 "N/A" 还标记 success=True。"""
    orchestrator = ToolOrchestrator()
    orchestrator.sources['price'] = [
        DataSource('mock_success', mock_source_success, 1, 60),
    ]
    orchestrator.cache.set_negative("price:BADTKR", "not found: invalid symbol")

    result = orchestrator.fetch('price', 'BADTKR')

    assert result.success is False
    assert result.source == 'negative_cache'
    assert result.data is None  # 错误载荷不得冒充数据
    assert "not found" in (result.error or "")


def test_validation_integration():
    """测试数据验证集成"""
    orchestrator = ToolOrchestrator()
    
    def invalid_data_source(ticker: str) -> str:
        return "Error: Data not available"
    
    orchestrator.sources['price'] = [
        DataSource('invalid', invalid_data_source, 1, 60),
        DataSource('valid', mock_source_success, 2, 60),
    ]
    
    result = orchestrator.fetch('price', 'AAPL')
    
    # 应该跳过无效数据源，使用有效的
    assert result.success == True
    assert result.source == 'valid'
    assert result.validation is not None
    assert result.validation.is_valid == True
    
    print("[OK] 数据验证集成测试通过")


def test_reset_stats():
    """测试重置统计"""
    orchestrator = ToolOrchestrator()
    orchestrator.sources['price'] = [
        DataSource('mock_success', mock_source_success, 1, 60),
    ]
    
    # 产生一些统计
    orchestrator.fetch('price', 'AAPL')
    orchestrator.fetch('price', 'GOOGL')
    
    stats = orchestrator.get_stats()
    assert stats['orchestrator']['total_requests'] == 2
    
    # 重置
    orchestrator.reset_stats()
    
    stats = orchestrator.get_stats()
    assert stats['orchestrator']['total_requests'] == 0
    
    print("[OK] 重置统计测试通过")


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("Step 1.3 测试 - ToolOrchestrator 单元测试")
    print("=" * 60)
    print()
    
    tests = [
        ("编排器初始化", test_orchestrator_init),
        ("手动注册数据源", test_manual_source_registration),
        ("成功获取数据", test_fetch_success),
        ("失败回退", test_fetch_with_fallback),
        ("所有数据源失败", test_fetch_all_fail),
        ("缓存集成", test_cache_integration),
        ("限速处理", test_rate_limit_handling),
        ("None 结果处理", test_none_result_handling),
        ("连续失败优先级降低", test_consecutive_failures_priority),
        ("统计追踪", test_stats_tracking),
        ("数据验证集成", test_validation_integration),
        ("重置统计", test_reset_stats),
    ]
    
    results = {}
    for test_name, test_func in tests:
        try:
            test_func()
            results[test_name] = True
        except Exception as e:
            print(f"[FAIL] {test_name} 测试失败: {type(e).__name__}")
            results[test_name] = False
    
    print()
    print("=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "[OK] 通过" if result else "[FAIL] 失败"
        print(f"  {test_name}: {status}")
    
    print()
    print(f"总计: {passed}/{total} 测试通过")
    
    if passed == total:
        print("\n Step 1.3 ToolOrchestrator 测试全部通过！")
        return True
    else:
        print("\nWARNING 部分测试失败，请修复后再继续。")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
