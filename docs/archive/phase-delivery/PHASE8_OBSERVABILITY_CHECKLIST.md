# PHASE8_OBSERVABILITY_CHECKLIST.md

**生成时间**：2026-06-09  
**阶段**：Phase 8 — 可观测性检查清单  
**结论**：PARTIAL（日志/健康检查已内置；指标/告警需生产部署时补充）

---

## 1. 日志（Logging）

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 后端请求日志 | ✅ 内置 | FastAPI access log，包含 method/path/status/latency |
| 错误堆栈日志 | ✅ 内置 | Python traceback via uvicorn stderr |
| 结构化日志（JSON） | ⚠️ 部分 | 当前为文本格式，生产建议切换 JSON |
| 日志级别可配置 | ✅ 支持 | `LOG_LEVEL` 环境变量 |
| Docker 日志驱动 | ⚠️ 默认（json-file） | 生产建议配置 max-size/max-file |
| 日志聚合（ELK/Loki） | ⚠️ NOT_CONFIGURED | 按需配置，非必须 |

**日志查看命令**：
```bash
# 实时后端日志
docker logs -f finsight-backend

# 最近错误
docker logs --tail=200 finsight-backend 2>&1 | grep -E "ERROR|Exception|Traceback"

# 访问日志（nginx 前端）
docker logs --tail=100 finsight-frontend
```

---

## 2. 健康检查（Health Checks）

| 检查项 | 状态 | 说明 |
|--------|------|------|
| `/api/health` 端点 | ✅ 实现 | 返回 `{"status": "ok", "version": "..."}` |
| Docker healthcheck | ✅ 配置 | `docker-compose.yml` 中 `healthcheck` 字段已配置 |
| 数据库连通性检查 | ✅ postgres `pg_isready` | smoke 中已验证 |
| 健康检查周期 | ✅ 30s 间隔，3 次重试 | 符合生产要求 |
| 外部健康检查（Uptime Robot 等） | ⚠️ NOT_CONFIGURED | 生产部署时按需配置 |

---

## 3. 性能指标（Metrics）

| 指标 | 状态 | 说明 |
|------|------|------|
| P95 API 延迟 | ✅ VERIFIED | Phase 7 recheck：全端点 P95 < 30ms |
| Prometheus metrics | ⚠️ NOT_CONFIGURED | FastAPI 可通过 `prometheus-fastapi-instrumentator` 添加 |
| 数据库查询时间 | ⚠️ 无内置 | 生产建议启用 `log_min_duration_statement=200` |
| 容器资源使用 | ⚠️ 手动查看 | `docker stats finsight-backend finsight-postgres` |

**当前手动性能检查**：
```bash
# 实时容器资源
docker stats --no-stream finsight-backend finsight-postgres finsight-frontend

# API 延迟抽样
for endpoint in /api/health /api/today /api/portfolio/summary; do
  time curl -s "http://localhost:8000$endpoint?session_id=test" > /dev/null
done
```

---

## 4. 告警（Alerting）

| 告警规则 | 状态 | 说明 |
|---------|------|------|
| 后端容器 unhealthy | ⚠️ NOT_CONFIGURED | 需 Docker 事件监听或外部监控 |
| API 错误率 > 1% | ⚠️ NOT_CONFIGURED | 需 Prometheus AlertManager 或等效 |
| 磁盘使用率 > 80% | ⚠️ NOT_CONFIGURED | 需系统监控 |
| DB 连接池满 | ⚠️ NOT_CONFIGURED | 需 pg_stat_activity 监控 |
| SSL 证书到期 | ⚠️ NOT_CONFIGURED | 需 certbot 或外部监控 |

**应急告警（最小化配置）**：
```bash
# 简单存活检查脚本（可加入 cron 每 5 分钟执行）
#!/bin/bash
STATUS=$(curl -sf http://localhost:8000/api/health | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('status')=='ok' else 1)")
if [ $? -ne 0 ]; then
  echo "[ALERT $(date)] FinSight backend unhealthy!" | mail -s "FinSight ALERT" admin@example.com
fi
```

---

## 5. 追踪（Tracing）

| 项目 | 状态 | 说明 |
|------|------|------|
| 请求 ID | ⚠️ 部分 | FastAPI 可通过 middleware 添加 X-Request-ID |
| 分布式追踪（OpenTelemetry） | ⚠️ NOT_CONFIGURED | 当前单体部署暂不需要 |

---

## 6. 仪表板（Dashboard）

| 仪表板 | 状态 | 说明 |
|--------|------|------|
| Grafana | ⚠️ NOT_CONFIGURED | 可通过 `prometheus-fastapi-instrumentator` + Grafana 部署 |
| Docker Dashboard | ✅ Docker Desktop | 本地开发可用 |

---

## 7. 生产可观测性最低要求（上线前完成）

| 优先级 | 项目 | 工具建议 |
|--------|------|---------|
| P0 | 健康检查外部监控 | Uptime Robot（免费）/ Better Uptime |
| P0 | 错误日志告警 | Sentry（免费 tier）/ 钉钉/飞书 webhook |
| P1 | 性能指标收集 | `prometheus-fastapi-instrumentator` + Grafana |
| P1 | 日志聚合 | Loki + Grafana，或 AWS CloudWatch |
| P2 | 分布式追踪 | OpenTelemetry + Tempo |

---

## 8. 快速接入 Sentry（推荐 P0 告警）

```bash
pip install sentry-sdk[fastapi]
```

```python
# backend/api/main.py 顶部添加（2 行）
import sentry_sdk
sentry_sdk.init(dsn="https://xxx@sentry.io/xxx", traces_sample_rate=0.1)
```

接入后自动捕获所有未处理异常并发送到 Sentry，零配置告警。
