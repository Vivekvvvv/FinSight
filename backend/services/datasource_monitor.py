"""
数据源健康监控服务

功能：
- 记录腾讯/Yahoo/Demo三个源的成功率
- 自动降级：腾讯财经连续失败3次→切换到demo
- 健康仪表盘：/api/system/health
- 持久化存储：定期保存到SQLite
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

logger = logging.getLogger(__name__)

# 延迟导入避免循环依赖
_storage = None

def _get_storage():
    global _storage
    if _storage is None:
        try:
            from backend.services.monitoring_storage import get_storage
            _storage = get_storage()
        except Exception as e:
            logger.warning(f"监控存储初始化失败: {e}")
            _storage = False  # 标记为失败，避免重复尝试
    return _storage if _storage is not False else None

DataSourceType = Literal["tencent", "yahoo", "demo", "unknown"]


@dataclass
class DataSourceMetrics:
    """单个数据源的监控指标"""

    name: DataSourceType
    total_requests: int = 0
    success_count: int = 0
    failure_count: int = 0
    consecutive_failures: int = 0
    last_success_at: str | None = None
    last_failure_at: str | None = None
    avg_response_time_ms: float = 0.0
    response_times: list[float] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """成功率百分比"""
        if self.total_requests == 0:
            return 0.0
        return (self.success_count / self.total_requests) * 100

    @property
    def is_healthy(self) -> bool:
        """健康状态：成功率>80% 且连续失败<3次"""
        return self.success_rate >= 80.0 and self.consecutive_failures < 3

    @property
    def status(self) -> str:
        """状态标签"""
        if self.consecutive_failures >= 3:
            return "degraded"
        elif self.success_rate >= 90:
            return "healthy"
        elif self.success_rate >= 70:
            return "warning"
        else:
            return "critical"


class DataSourceMonitor:
    """数据源健康监控器"""

    def __init__(self):
        self._metrics: dict[DataSourceType, DataSourceMetrics] = {
            "tencent": DataSourceMetrics("tencent"),
            "yahoo": DataSourceMetrics("yahoo"),
            "demo": DataSourceMetrics("demo"),
            "unknown": DataSourceMetrics("unknown"),
        }
        self._degraded_sources: set[DataSourceType] = set()

    def record_success(self, source: DataSourceType, response_time_ms: float = 0.0):
        """记录成功请求"""
        if source not in self._metrics:
            return

        m = self._metrics[source]
        m.total_requests += 1
        m.success_count += 1
        m.consecutive_failures = 0  # 重置连续失败计数
        m.last_success_at = datetime.now(timezone.utc).isoformat()

        # 记录响应时间
        if response_time_ms > 0:
            m.response_times.append(response_time_ms)
            # 保留最近100次
            if len(m.response_times) > 100:
                m.response_times.pop(0)
            m.avg_response_time_ms = sum(m.response_times) / len(m.response_times)

        # 成功后可能恢复健康状态
        if source in self._degraded_sources and m.is_healthy:
            self._degraded_sources.discard(source)
            logger.info(f"[Monitor] {source} 已恢复健康状态")

    def record_failure(self, source: DataSourceType, error_msg: str = ""):
        """记录失败请求"""
        if source not in self._metrics:
            return

        m = self._metrics[source]
        m.total_requests += 1
        m.failure_count += 1
        m.consecutive_failures += 1
        m.last_failure_at = datetime.now(timezone.utc).isoformat()

        # 连续失败3次触发降级
        if m.consecutive_failures >= 3 and source not in self._degraded_sources:
            self._degraded_sources.add(source)
            logger.warning(
                f"[Monitor] {source} 连续失败{m.consecutive_failures}次，触发降级。"
                f"成功率: {m.success_rate:.1f}% | 错误: {error_msg}"
            )

    def should_use_source(self, source: DataSourceType) -> bool:
        """判断是否应该使用该数据源"""
        if source == "demo":
            return True  # Demo总是可用
        return source not in self._degraded_sources

    def get_preferred_source(self, symbol: str) -> DataSourceType:
        """获取推荐数据源"""
        from backend.tools.tencent_provider import is_cn_symbol

        # A股优先腾讯
        if is_cn_symbol(symbol):
            if self.should_use_source("tencent"):
                return "tencent"
            else:
                return "demo"

        # 海外股票优先Yahoo
        if self.should_use_source("yahoo"):
            return "yahoo"

        return "demo"

    def get_health_report(self) -> dict[str, Any]:
        """生成健康报告并持久化"""
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "overall_status": self._calculate_overall_status(),
            "degraded_sources": list(self._degraded_sources),
            "sources": {
                name: {
                    "status": m.status,
                    "total_requests": m.total_requests,
                    "success_count": m.success_count,
                    "failure_count": m.failure_count,
                    "success_rate": round(m.success_rate, 2),
                    "consecutive_failures": m.consecutive_failures,
                    "last_success_at": m.last_success_at,
                    "last_failure_at": m.last_failure_at,
                    "avg_response_time_ms": round(m.avg_response_time_ms, 2),
                    "is_healthy": m.is_healthy,
                }
                for name, m in self._metrics.items()
            },
        }

        # 持久化存储（异步，不阻塞主流程）
        try:
            storage = _get_storage()
            if storage:
                storage.save_health_snapshot(report["sources"])
        except Exception as e:
            logger.debug(f"监控数据持久化失败（非致命）: {e}")

        return report

    def _calculate_overall_status(self) -> str:
        """计算整体状态"""
        if len(self._degraded_sources) >= 2:
            return "critical"
        elif len(self._degraded_sources) == 1:
            return "degraded"

        # 检查各源成功率
        avg_success_rate = sum(m.success_rate for m in self._metrics.values()) / len(self._metrics)
        if avg_success_rate >= 90:
            return "healthy"
        elif avg_success_rate >= 70:
            return "warning"
        else:
            return "degraded"

    def reset_stats(self):
        """重置统计数据（用于测试）"""
        for m in self._metrics.values():
            m.total_requests = 0
            m.success_count = 0
            m.failure_count = 0
            m.consecutive_failures = 0
            m.last_success_at = None
            m.last_failure_at = None
            m.avg_response_time_ms = 0.0
            m.response_times.clear()
        self._degraded_sources.clear()


# 全局单例
_monitor: DataSourceMonitor | None = None


def get_monitor() -> DataSourceMonitor:
    """获取全局监控器实例"""
    global _monitor
    if _monitor is None:
        _monitor = DataSourceMonitor()
    return _monitor


__all__ = ["DataSourceMonitor", "get_monitor", "DataSourceType"]
