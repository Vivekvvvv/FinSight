"""
Prometheus Exporter for FinSight API monitoring.
Exports custom metrics for API performance, data source health, and cache efficiency.
"""

from prometheus_client import Counter, Histogram, Gauge, Info, CollectorRegistry, generate_latest
from prometheus_client.exposition import CONTENT_TYPE_LATEST
from fastapi import APIRouter, Response
from typing import Optional
import time

# 创建自定义注册表
registry = CollectorRegistry()

# ============================================================================
# API 请求指标
# ============================================================================

# API请求总数（按端点、方法、状态码分类）
api_requests_total = Counter(
    'finsight_api_requests_total',
    'Total number of API requests',
    ['method', 'endpoint', 'status_code'],
    registry=registry
)

# API响应时间直方图（按端点分类）
api_request_duration_seconds = Histogram(
    'finsight_api_request_duration_seconds',
    'API request duration in seconds',
    ['method', 'endpoint'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
    registry=registry
)

# API错误率
api_errors_total = Counter(
    'finsight_api_errors_total',
    'Total number of API errors',
    ['method', 'endpoint', 'error_type'],
    registry=registry
)

# ============================================================================
# 数据源健康指标
# ============================================================================

# 数据源健康状态（0=down, 1=degraded, 2=healthy）
data_source_health_status = Gauge(
    'finsight_data_source_health_status',
    'Data source health status (0=down, 1=degraded, 2=healthy)',
    ['source_name'],
    registry=registry
)

# 数据源成功率（0-100%）
data_source_success_rate = Gauge(
    'finsight_data_source_success_rate',
    'Data source success rate percentage',
    ['source_name'],
    registry=registry
)

# 数据源平均响应时间（毫秒）
data_source_response_time_ms = Gauge(
    'finsight_data_source_response_time_ms',
    'Data source average response time in milliseconds',
    ['source_name'],
    registry=registry
)

# 数据源请求总数
data_source_requests_total = Counter(
    'finsight_data_source_requests_total',
    'Total number of data source requests',
    ['source_name', 'status'],
    registry=registry
)

# ============================================================================
# 缓存效率指标
# ============================================================================

# 缓存命中总数
cache_hits_total = Counter(
    'finsight_cache_hits_total',
    'Total number of cache hits',
    ['cache_key_prefix'],
    registry=registry
)

# 缓存未命中总数
cache_misses_total = Counter(
    'finsight_cache_misses_total',
    'Total number of cache misses',
    ['cache_key_prefix'],
    registry=registry
)

# 缓存命中率
cache_hit_rate = Gauge(
    'finsight_cache_hit_rate',
    'Cache hit rate percentage',
    ['cache_key_prefix'],
    registry=registry
)

# 缓存大小（当前缓存的键数量）
cache_size = Gauge(
    'finsight_cache_size',
    'Number of cached keys',
    registry=registry
)

# 缓存过期总数
cache_expirations_total = Counter(
    'finsight_cache_expirations_total',
    'Total number of cache expirations',
    registry=registry
)

# ============================================================================
# 系统信息指标
# ============================================================================

# 应用信息
app_info = Info(
    'finsight_app',
    'FinSight application information',
    registry=registry
)

# 应用启动时间（Unix时间戳）
app_start_time = Gauge(
    'finsight_app_start_time_seconds',
    'Application start time in seconds since epoch',
    registry=registry
)

# 活跃请求数
active_requests = Gauge(
    'finsight_active_requests',
    'Number of active requests',
    registry=registry
)

# ============================================================================
# 业务指标
# ============================================================================

# 股票查询总数
stock_queries_total = Counter(
    'finsight_stock_queries_total',
    'Total number of stock queries',
    ['ticker', 'query_type'],
    registry=registry
)

# 用户会话数
user_sessions_active = Gauge(
    'finsight_user_sessions_active',
    'Number of active user sessions',
    registry=registry
)

# ============================================================================
# 工具函数
# ============================================================================

def init_app_info(version: str = "1.8.0", environment: str = "production"):
    """初始化应用信息"""
    app_info.info({
        'version': version,
        'environment': environment,
        'app_name': 'FinSight'
    })
    app_start_time.set(time.time())


def record_api_request(method: str, endpoint: str, status_code: int, duration: float):
    """记录API请求指标"""
    api_requests_total.labels(method=method, endpoint=endpoint, status_code=status_code).inc()
    api_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(duration)


def record_api_error(method: str, endpoint: str, error_type: str):
    """记录API错误"""
    api_errors_total.labels(method=method, endpoint=endpoint, error_type=error_type).inc()


def update_data_source_health(source_name: str, status: int, success_rate: float, response_time_ms: float):
    """更新数据源健康指标"""
    data_source_health_status.labels(source_name=source_name).set(status)
    data_source_success_rate.labels(source_name=source_name).set(success_rate)
    data_source_response_time_ms.labels(source_name=source_name).set(response_time_ms)


def record_data_source_request(source_name: str, success: bool):
    """记录数据源请求"""
    status = 'success' if success else 'failure'
    data_source_requests_total.labels(source_name=source_name, status=status).inc()


def record_cache_hit(cache_key_prefix: str):
    """记录缓存命中"""
    cache_hits_total.labels(cache_key_prefix=cache_key_prefix).inc()


def record_cache_miss(cache_key_prefix: str):
    """记录缓存未命中"""
    cache_misses_total.labels(cache_key_prefix=cache_key_prefix).inc()


def update_cache_hit_rate(cache_key_prefix: str, hit_rate: float):
    """更新缓存命中率"""
    cache_hit_rate.labels(cache_key_prefix=cache_key_prefix).set(hit_rate)


def update_cache_size(size: int):
    """更新缓存大小"""
    cache_size.set(size)


def record_cache_expiration():
    """记录缓存过期"""
    cache_expirations_total.inc()


def record_stock_query(ticker: str, query_type: str):
    """记录股票查询"""
    stock_queries_total.labels(ticker=ticker, query_type=query_type).inc()


def update_active_requests(delta: int):
    """更新活跃请求数"""
    if delta > 0:
        active_requests.inc(delta)
    elif delta < 0:
        active_requests.dec(abs(delta))


def update_active_sessions(count: int):
    """更新活跃会话数"""
    user_sessions_active.set(count)


# ============================================================================
# FastAPI 路由
# ============================================================================

router = APIRouter(prefix="/metrics", tags=["Monitoring"])


@router.get("")
async def metrics():
    """
    Prometheus metrics endpoint.
    Returns metrics in Prometheus text format.
    """
    metrics_output = generate_latest(registry)
    return Response(content=metrics_output, media_type=CONTENT_TYPE_LATEST)


# ============================================================================
# 中间件集成示例
# ============================================================================

class PrometheusMiddleware:
    """
    FastAPI middleware for automatic Prometheus metrics collection.
    Usage:
        from starlette.middleware.base import BaseHTTPMiddleware
        app.add_middleware(BaseHTTPMiddleware, dispatch=PrometheusMiddleware())
    """

    async def __call__(self, request, call_next):
        # 增加活跃请求计数
        update_active_requests(1)

        # 记录开始时间
        start_time = time.time()

        # 调用下一个中间件/路由
        try:
            response = await call_next(request)

            # 记录成功请求
            duration = time.time() - start_time
            record_api_request(
                method=request.method,
                endpoint=request.url.path,
                status_code=response.status_code,
                duration=duration
            )

            return response

        except Exception as e:
            # 记录错误
            duration = time.time() - start_time
            error_type = type(e).__name__

            record_api_error(
                method=request.method,
                endpoint=request.url.path,
                error_type=error_type
            )

            record_api_request(
                method=request.method,
                endpoint=request.url.path,
                status_code=500,
                duration=duration
            )

            raise

        finally:
            # 减少活跃请求计数
            update_active_requests(-1)
