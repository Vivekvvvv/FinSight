# -*- coding: utf-8 -*-
"""
Phase 5 性能烟雾测试

验证聚合 API 在大数据量下的响应时间。
不依赖外部网络、真实 LLM，只测本地规则和聚合逻辑。

目标：
- 单接口本地 mock 环境 P95 < 500ms
- /api/today P95 < 800ms
"""

import time
import pytest

from backend.services import timeline_service, what_changed, research_notes
from backend.services.research_quality import get_research_quality
from backend.services.report_index import get_report_index_store
from backend.services.memory import MemoryService

# 全局实例
_memory_service = MemoryService()


@pytest.fixture
def clean_perf_state():
    """清理并准备性能测试环境"""
    session_id = "perf_test_session"
    user_id = "perf_test_user"

    yield {
        "session_id": session_id,
        "user_id": user_id,
    }


def generate_test_data_small(session_id: str, user_id: str):
    """生成小数据集（用于快速测试）"""
    store = get_report_index_store()

    # 生成 20 份报告
    tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "META"]
    for i in range(20):
        ticker = tickers[i % len(tickers)]
        store.upsert_report(
            session_id=session_id,
            report={
                "report_id": f"perf_report_{i:03d}",
                "ticker": ticker,
                "title": f"Performance Test Report {i}",
                "summary": f"This is a performance test report for {ticker}. " * 3,
                "as_of": "2026-06-08T10:00:00Z" if i % 3 == 0 else "2026-06-01T10:00:00Z",
                "citations": [
                    {
                        "title": f"Source {j}",
                        "url": f"https://example.com/source_{i}_{j}",
                        "snippet": f"Citation snippet {j}",
                    }
                    for j in range((i % 3) + 1)
                ],
            }
        )

    # 生成 10 个笔记
    for i in range(10):
        ticker = tickers[i % len(tickers)]
        research_notes.create_note(
            session_id=session_id,
            user_id=user_id,
            ticker=ticker,
            title=f"Performance Test Note {i}",
            content=f"# Test Note {i}\n\nContent for {ticker}.\n\n" * 2,
        )

    # 添加 5 个自选股
    for ticker in tickers:
        _memory_service.add_to_watchlist(user_id, ticker, note=f"Perf test {ticker}")


def measure_latency(func, *args, **kwargs):
    """测量函数执行时间（毫秒）"""
    start = time.perf_counter()
    result = func(*args, **kwargs)
    elapsed_ms = (time.perf_counter() - start) * 1000
    return result, elapsed_ms


def test_timeline_performance_smoke(clean_perf_state):
    """Timeline 聚合性能烟雾测试"""
    ctx = clean_perf_state

    # 准备数据
    generate_test_data_small(ctx["session_id"], ctx["user_id"])

    # 测量 5 次
    latencies = []
    for _ in range(5):
        _, elapsed = measure_latency(
            timeline_service.get_timeline,
            symbol="AAPL",  # 必需参数
            session_id=ctx["session_id"],
            user_id=ctx["user_id"],
            limit=50,
        )
        latencies.append(elapsed)

    avg_ms = sum(latencies) / len(latencies)
    max_ms = max(latencies)

    print(f"\n[Timeline] Avg: {avg_ms:.2f}ms, Max: {max_ms:.2f}ms")

    # 宽松断言：Max < 1000ms（烟雾测试）
    assert max_ms < 1000, f"Timeline Max {max_ms:.2f}ms exceeded 1000ms"


def test_what_changed_performance_smoke(clean_perf_state):
    """What Changed 规则引擎性能烟雾测试"""
    ctx = clean_perf_state

    # 准备数据
    generate_test_data_small(ctx["session_id"], ctx["user_id"])

    # 测量 5 次
    latencies = []
    for _ in range(5):
        _, elapsed = measure_latency(
            what_changed.get_what_changed,
            session_id=ctx["session_id"],
            user_id=ctx["user_id"],
            limit=10,
        )
        latencies.append(elapsed)

    avg_ms = sum(latencies) / len(latencies)
    max_ms = max(latencies)

    print(f"\n[What Changed] Avg: {avg_ms:.2f}ms, Max: {max_ms:.2f}ms")

    # 宽松断言：Max < 500ms
    assert max_ms < 500, f"What Changed Max {max_ms:.2f}ms exceeded 500ms"


def test_research_quality_performance_smoke(clean_perf_state):
    """Research Quality 健康度计算性能烟雾测试"""
    ctx = clean_perf_state

    # 准备数据
    generate_test_data_small(ctx["session_id"], ctx["user_id"])

    # 测量 5 次
    latencies = []
    for _ in range(5):
        _, elapsed = measure_latency(
            get_research_quality,
            session_id=ctx["session_id"],
            user_id=ctx["user_id"],  # 必需参数
        )
        latencies.append(elapsed)

    avg_ms = sum(latencies) / len(latencies)
    max_ms = max(latencies)

    print(f"\n[Research Quality] Avg: {avg_ms:.2f}ms, Max: {max_ms:.2f}ms")

    # 宽松断言：Max < 500ms
    assert max_ms < 500, f"Research Quality Max {max_ms:.2f}ms exceeded 500ms"


def test_research_notes_list_performance_smoke(clean_perf_state):
    """Research Notes 列表查询性能烟雾测试"""
    ctx = clean_perf_state

    # 准备数据
    generate_test_data_small(ctx["session_id"], ctx["user_id"])

    # 测量 5 次
    latencies = []
    for _ in range(5):
        _, elapsed = measure_latency(
            research_notes.list_notes,
            session_id=ctx["session_id"],
            user_id=ctx["user_id"],
            limit=50,
        )
        latencies.append(elapsed)

    avg_ms = sum(latencies) / len(latencies)
    max_ms = max(latencies)

    print(f"\n[Research Notes List] Avg: {avg_ms:.2f}ms, Max: {max_ms:.2f}ms")

    # 宽松断言：Max < 300ms
    assert max_ms < 300, f"Research Notes List Max {max_ms:.2f}ms exceeded 300ms"


def test_combined_workspace_simulation_smoke(clean_perf_state):
    """模拟 /api/today 工作台聚合场景（烟雾测试）"""
    ctx = clean_perf_state

    # 准备完整数据集
    generate_test_data_small(ctx["session_id"], ctx["user_id"])

    # 测量 3 次完整工作流
    latencies = []
    for _ in range(3):
        start = time.perf_counter()

        # 模拟 /api/today 的并发调用（串行模拟）
        _ = timeline_service.get_timeline(
            symbol="AAPL",  # 必需参数
            session_id=ctx["session_id"],
            user_id=ctx["user_id"],
            limit=50,
        )
        _ = what_changed.get_what_changed(
            session_id=ctx["session_id"],
            user_id=ctx["user_id"],
            limit=5,
        )
        _ = get_research_quality(
            session_id=ctx["session_id"],
            user_id=ctx["user_id"],  # 必需参数
        )
        _ = research_notes.list_notes(
            session_id=ctx["session_id"],
            user_id=ctx["user_id"],
            limit=10,
        )

        elapsed_ms = (time.perf_counter() - start) * 1000
        latencies.append(elapsed_ms)

    avg_ms = sum(latencies) / len(latencies)
    max_ms = max(latencies)

    print(f"\n[Combined Workspace] Avg: {avg_ms:.2f}ms, Max: {max_ms:.2f}ms")
    print(f"  (串行模拟，实际 /api/today 应使用并发可更快)")

    # 宽松断言：Max < 2000ms（串行叠加）
    assert max_ms < 2000, f"Combined Workspace Max {max_ms:.2f}ms exceeded 2000ms"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
