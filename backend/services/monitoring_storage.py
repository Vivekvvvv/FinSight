"""
监控数据持久化服务

功能：
- 使用SQLite存储历史监控数据
- 保留最近30天数据，自动清理过期记录
- 支持历史趋势查询（7天/30天）
- 提供聚合统计接口（每小时/每天）
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from backend.utils.quote import safe_float, safe_int

logger = logging.getLogger(__name__)

# 数据库路径（项目根目录/data/monitoring.db）
DB_PATH = Path(__file__).parent.parent.parent / "data" / "monitoring.db"

# 进程级串行化 + WAL/超时，对齐 portfolio_store 的并发安全模式。
# get_storage() 是进程单例：写（/api/system/health）与读（trend/stats 端点）
# 并发时，裸 sqlite3.connect（rollback journal + 默认 5s 超时、无锁）会抛
# "database is locked"，而读端点无 try/except → 直接 HTTP 500（R55）。
_lock = threading.RLock()


def _connect(db_path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


class MonitoringStorage:
    """监控数据存储层"""

    def __init__(self, db_path: Path | str = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _init_database(self) -> None:
        """初始化数据库表结构"""
        with _lock, _connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS health_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    success_rate REAL NOT NULL,
                    avg_response_time_ms REAL NOT NULL,
                    total_requests INTEGER NOT NULL,
                    success_count INTEGER NOT NULL,
                    failure_count INTEGER NOT NULL,
                    consecutive_failures INTEGER NOT NULL,
                    is_healthy INTEGER NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 创建索引加速查询
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp
                ON health_records(timestamp DESC)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_source_timestamp
                ON health_records(source_name, timestamp DESC)
            """)

            conn.commit()
            logger.info(f"监控数据库初始化完成: {self.db_path}")

    def save_health_snapshot(self, sources: dict[str, dict[str, Any]]) -> None:
        """
        保存健康快照

        Args:
            sources: 数据源健康状态字典，格式同 DataSourceMonitor.get_health_report()['sources']

        Example:
            storage.save_health_snapshot({
                "tencent": {
                    "status": "healthy",
                    "success_rate": 98.5,
                    "avg_response_time_ms": 45.2,
                    "total_requests": 1000,
                    "success_count": 985,
                    "failure_count": 15,
                    "consecutive_failures": 0,
                    "is_healthy": True
                }
            })
        """
        timestamp = datetime.utcnow().isoformat()

        with _lock, _connect(self.db_path) as conn:
            for source_name, data in sources.items():
                conn.execute("""
                    INSERT INTO health_records (
                        timestamp, source_name, status, success_rate,
                        avg_response_time_ms, total_requests, success_count,
                        failure_count, consecutive_failures, is_healthy
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    timestamp,
                    source_name,
                    data.get("status", "unknown"),
                    safe_float(data.get("success_rate")) or 0.0,
                    safe_float(data.get("avg_response_time_ms")) or 0.0,
                    safe_int(data.get("total_requests"), 0) or 0,
                    safe_int(data.get("success_count"), 0) or 0,
                    safe_int(data.get("failure_count"), 0) or 0,
                    safe_int(data.get("consecutive_failures"), 0) or 0,
                    1 if data.get("is_healthy", False) else 0
                ))
            conn.commit()

    def get_trend(
        self,
        source_name: str | None = None,
        days: int = 7
    ) -> list[dict[str, Any]]:
        """
        查询历史趋势数据

        Args:
            source_name: 数据源名称，None表示查询所有源
            days: 查询天数（默认7天）

        Returns:
            历史记录列表，按时间倒序

        Example:
            >>> storage.get_trend("tencent", days=7)
            [
                {
                    "timestamp": "2026-06-15T12:00:00",
                    "source_name": "tencent",
                    "status": "healthy",
                    "success_rate": 98.5,
                    "avg_response_time_ms": 45.2,
                    "is_healthy": True
                },
                ...
            ]
        """
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

        with _lock, _connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            if source_name:
                cursor = conn.execute("""
                    SELECT
                        timestamp, source_name, status, success_rate,
                        avg_response_time_ms, total_requests, success_count,
                        failure_count, consecutive_failures, is_healthy
                    FROM health_records
                    WHERE source_name = ? AND timestamp >= ?
                    ORDER BY timestamp DESC
                """, (source_name, cutoff))
            else:
                cursor = conn.execute("""
                    SELECT
                        timestamp, source_name, status, success_rate,
                        avg_response_time_ms, total_requests, success_count,
                        failure_count, consecutive_failures, is_healthy
                    FROM health_records
                    WHERE timestamp >= ?
                    ORDER BY timestamp DESC
                """, (cutoff,))

            return [dict(row) for row in cursor.fetchall()]

    def get_hourly_aggregation(
        self,
        source_name: str,
        hours: int = 24
    ) -> list[dict[str, Any]]:
        """
        查询每小时聚合统计

        Args:
            source_name: 数据源名称
            hours: 查询小时数（默认24小时）

        Returns:
            每小时平均值列表

        Example:
            >>> storage.get_hourly_aggregation("tencent", hours=24)
            [
                {
                    "hour": "2026-06-15 12:00",
                    "avg_success_rate": 98.2,
                    "avg_response_time_ms": 46.5,
                    "sample_count": 120
                },
                ...
            ]
        """
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()

        with _lock, _connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT
                    strftime('%Y-%m-%d %H:00', timestamp) as hour,
                    AVG(success_rate) as avg_success_rate,
                    AVG(avg_response_time_ms) as avg_response_time_ms,
                    COUNT(*) as sample_count
                FROM health_records
                WHERE source_name = ? AND timestamp >= ?
                GROUP BY hour
                ORDER BY hour DESC
            """, (source_name, cutoff))

            return [dict(row) for row in cursor.fetchall()]

    def cleanup_old_records(self, keep_days: int = 30) -> int:
        """
        清理过期记录

        Args:
            keep_days: 保留天数（默认30天）

        Returns:
            删除的记录数量

        Example:
            >>> deleted = storage.cleanup_old_records(keep_days=30)
            >>> print(f"已清理 {deleted} 条过期记录")
        """
        cutoff = (datetime.utcnow() - timedelta(days=keep_days)).isoformat()

        with _lock, _connect(self.db_path) as conn:
            cursor = conn.execute("""
                DELETE FROM health_records
                WHERE timestamp < ?
            """, (cutoff,))
            conn.commit()
            deleted = cursor.rowcount

        if deleted > 0:
            logger.info(f"已清理 {deleted} 条超过 {keep_days} 天的监控记录")

        return deleted

    def get_stats(self) -> dict[str, Any]:
        """
        获取数据库统计信息

        Returns:
            统计信息字典

        Example:
            >>> stats = storage.get_stats()
            >>> print(f"总记录数: {stats['total_records']}")
        """
        with _lock, _connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT
                    COUNT(*) as total_records,
                    COUNT(DISTINCT source_name) as source_count,
                    MIN(timestamp) as oldest_record,
                    MAX(timestamp) as newest_record
                FROM health_records
            """)
            row = cursor.fetchone()

            return {
                "total_records": row[0],
                "source_count": row[1],
                "oldest_record": row[2],
                "newest_record": row[3],
                "db_path": str(self.db_path),
                "db_size_bytes": self.db_path.stat().st_size if self.db_path.exists() else 0
            }


# 全局单例
_storage_instance: MonitoringStorage | None = None


def get_storage() -> MonitoringStorage:
    """获取全局存储实例（单例模式）"""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = MonitoringStorage()
    return _storage_instance


__all__ = ["MonitoringStorage", "get_storage"]
