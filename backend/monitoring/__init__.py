"""
Monitoring package initialization.
Exports Prometheus metrics and middleware.
"""

from .prometheus_exporter import (
    router as metrics_router,
    PrometheusMiddleware,
    init_app_info,
    record_api_request,
    record_api_error,
    update_data_source_health,
    record_data_source_request,
    record_cache_hit,
    record_cache_miss,
    update_cache_hit_rate,
    update_cache_size,
    record_cache_expiration,
    record_stock_query,
    update_active_requests,
    update_active_sessions,
)

__all__ = [
    'metrics_router',
    'PrometheusMiddleware',
    'init_app_info',
    'record_api_request',
    'record_api_error',
    'update_data_source_health',
    'record_data_source_request',
    'record_cache_hit',
    'record_cache_miss',
    'update_cache_hit_rate',
    'update_cache_size',
    'record_cache_expiration',
    'record_stock_query',
    'update_active_requests',
    'update_active_sessions',
]
