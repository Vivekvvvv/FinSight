# FinSight Prometheus监控集成

## 概述

FinSight已集成Prometheus + Grafana监控栈，用于实时监控API性能、数据源健康和缓存效率。

## 目录结构

```
monitoring/
├── prometheus.yml              # Prometheus配置
├── docker-compose.yml          # Docker Compose编排
├── rules/
│   └── alerts.yml             # 告警规则
└── grafana/
    ├── dashboards/
    │   └── finsight-metrics.json  # Grafana仪表盘
    └── provisioning/
        ├── datasources/
        │   └── prometheus.yml     # 数据源配置
        └── dashboards/
            └── default.yml        # 仪表盘配置
```

## 快速开始

### 1. 启动监控栈

```bash
cd monitoring
docker-compose up -d
```

### 2. 访问监控界面

- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000
  - 默认用户名：admin
  - 默认密码：admin

### 3. 启动FinSight API

```bash
cd backend
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

### 4. 查看指标

访问 http://localhost:8000/metrics 查看原始Prometheus指标。

## 监控指标

### API性能指标

| 指标名称 | 类型 | 说明 |
|---------|------|------|
| `finsight_api_requests_total` | Counter | API请求总数（按方法、端点、状态码） |
| `finsight_api_request_duration_seconds` | Histogram | API响应时间分布 |
| `finsight_api_errors_total` | Counter | API错误总数 |
| `finsight_active_requests` | Gauge | 当前活跃请求数 |

### 数据源健康指标

| 指标名称 | 类型 | 说明 |
|---------|------|------|
| `finsight_data_source_health_status` | Gauge | 数据源健康状态（0=down, 1=degraded, 2=healthy） |
| `finsight_data_source_success_rate` | Gauge | 数据源成功率(%) |
| `finsight_data_source_response_time_ms` | Gauge | 数据源平均响应时间(ms) |
| `finsight_data_source_requests_total` | Counter | 数据源请求总数 |

### 缓存效率指标

| 指标名称 | 类型 | 说明 |
|---------|------|------|
| `finsight_cache_hits_total` | Counter | 缓存命中总数 |
| `finsight_cache_misses_total` | Counter | 缓存未命中总数 |
| `finsight_cache_hit_rate` | Gauge | 缓存命中率(%) |
| `finsight_cache_size` | Gauge | 缓存键数量 |

### 业务指标

| 指标名称 | 类型 | 说明 |
|---------|------|------|
| `finsight_stock_queries_total` | Counter | 股票查询总数 |
| `finsight_user_sessions_active` | Gauge | 活跃用户会话数 |

## 告警规则

### 1. API告警

- **HighAPIErrorRate**: API错误率>5%，持续2分钟
- **SlowAPIResponse**: P95响应时间>2秒，持续3分钟
- **HighActiveRequests**: 活跃请求数>100，持续5分钟

### 2. 数据源告警

- **DataSourceDegraded**: 数据源健康状态<2，持续5分钟
- **DataSourceDown**: 数据源完全不可用，持续2分钟（严重）
- **LowDataSourceSuccessRate**: 成功率<80%，持续10分钟
- **SlowDataSourceResponse**: 响应时间>3秒，持续5分钟

### 3. 缓存告警

- **LowCacheHitRate**: 缓存命中率<50%，持续10分钟

## Grafana仪表盘

### 面板概览

1. **API请求速率（QPS）**: 实时显示各端点的请求速率
2. **API响应时间 P95**: 各端点的95分位响应时间
3. **数据源成功率**: 各数据源的成功率趋势
4. **数据源健康状态**: 当前健康状态（DOWN/DEGRADED/HEALTHY）
5. **缓存命中率**: 各缓存前缀的命中率
6. **活跃请求数**: 当前并发请求数

### 自定义查询示例

```promql
# API错误率（5分钟）
sum(rate(finsight_api_errors_total[5m]))
/
sum(rate(finsight_api_requests_total[5m]))

# P99响应时间
histogram_quantile(0.99,
  sum(rate(finsight_api_request_duration_seconds_bucket[5m])) by (le, endpoint)
)

# 数据源请求失败率
sum(rate(finsight_data_source_requests_total{status="failure"}[5m]))
/
sum(rate(finsight_data_source_requests_total[5m]))
```

## 代码集成

### 自动指标收集

Prometheus中间件已自动集成到FastAPI，无需手动埋点：

```python
# backend/api/main.py 已自动初始化
from backend.monitoring import init_app_info, metrics_router

# 应用启动时初始化
init_app_info(version="1.8.0", environment="production")

# 注册metrics端点
app.include_router(metrics_router)
```

### 手动埋点示例

```python
from backend.monitoring import (
    record_api_request,
    record_cache_hit,
    update_data_source_health,
    record_stock_query
)

# 记录API请求
record_api_request("GET", "/api/quote/AAPL", 200, 0.15)

# 记录缓存命中
record_cache_hit("quote")

# 更新数据源健康
update_data_source_health("tencent", status=2, success_rate=98.5, response_time_ms=120)

# 记录股票查询
record_stock_query("AAPL", "quote")
```

## 数据保留

- **Prometheus**: 30天（可在prometheus.yml中调整`--storage.tsdb.retention.time`）
- **Grafana**: 持久化到Docker Volume

## 故障排查

### Prometheus无法抓取指标

1. 检查FinSight API是否运行：`curl http://localhost:8000/metrics`
2. 检查Prometheus配置：`docker-compose exec prometheus cat /etc/prometheus/prometheus.yml`
3. 查看Prometheus日志：`docker-compose logs prometheus`

### Grafana无法连接Prometheus

1. 检查数据源配置：Grafana UI → Configuration → Data Sources
2. 测试连接：点击 "Test" 按钮
3. 查看Grafana日志：`docker-compose logs grafana`

### 告警未触发

1. 检查告警规则状态：Prometheus UI → Alerts
2. 验证规则语法：`promtool check rules monitoring/rules/alerts.yml`
3. 确认告警数据满足条件：直接在Prometheus查询

## 生产环境建议

1. **安全**: 
   - 修改Grafana默认密码
   - 启用HTTPS
   - 配置防火墙规则

2. **性能**:
   - 调整scrape_interval（默认15s）
   - 增加Prometheus内存限制
   - 配置远程存储（长期保留）

3. **告警**:
   - 集成Alertmanager（邮件、Slack、PagerDuty）
   - 配置告警分组和抑制规则
   - 设置维护窗口

4. **备份**:
   - 定期备份Prometheus数据：`prometheus-data` volume
   - 备份Grafana配置：`grafana-data` volume

## 相关文档

- [Prometheus官方文档](https://prometheus.io/docs/)
- [Grafana官方文档](https://grafana.com/docs/)
- [PromQL查询语言](https://prometheus.io/docs/prometheus/latest/querying/basics/)
