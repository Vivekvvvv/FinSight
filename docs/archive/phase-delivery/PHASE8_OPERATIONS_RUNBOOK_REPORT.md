# PHASE8_OPERATIONS_RUNBOOK_REPORT.md

**生成时间**：2026-06-09  
**阶段**：Phase 8 — 运维手册完整性报告  
**结论**：COMPLETE（备份 + 回滚手册已生成）

---

## 1. 已生成文档

| 文档 | 路径 | 说明 |
|------|------|------|
| 备份与恢复手册 | `docs/BACKUP_RESTORE_RUNBOOK.md` | pg_dump / rsync / 自动化备份脚本 |
| 回滚手册 | `docs/ROLLBACK_RUNBOOK.md` | 3 种回滚模式 + 决策矩阵 |

---

## 2. 备份手册关键内容

### 2.1 覆盖的备份类型

| 类型 | 方法 | 保留策略 |
|------|------|---------|
| PostgreSQL 逻辑备份 | `pg_dump --format=custom` | 30 天 |
| PostgreSQL 物理备份 | `pg_basebackup` | 按需 |
| 上传文件 | `tar -czf` / `rsync` | 30 天 |
| 环境配置 | `openssl enc -aes-256-cbc` | 永久（加密存储） |

### 2.2 自动化备份

提供 `scripts/backup.sh`，支持：
- 每日 02:00 cron 调用
- 自动保留 30 天
- 执行后输出时间戳日志

---

## 3. 回滚手册关键内容

### 3.1 三种回滚模式

| 模式 | 耗时 | 适用场景 |
|------|------|---------|
| 快速回滚（镜像切换） | 2-5 分钟 | 代码回归，无 schema 变更 |
| 完整回滚（镜像 + DB） | 10-20 分钟 | schema 变更导致数据不一致 |
| 紧急回滚（强制重建） | 1-2 分钟 | 容器崩溃循环无法正常关停 |

### 3.2 发布前必做项

每次发布前自动打 `previous` 标签：
```bash
docker tag finsight-backend:latest finsight-backend:previous
docker tag finsight-frontend:latest finsight-frontend:previous
```

### 3.3 安全边界

明确禁止 `docker compose down -v`（会删除数据卷）；回滚前必须先备份当前状态。

---

## 4. 运维最佳实践补充

### 4.1 日常检查命令

```bash
# 服务状态
docker compose ps

# 后端日志（最近 100 行）
docker logs --tail=100 finsight-backend

# 数据库连接数
docker exec finsight-postgres psql -U $POSTGRES_USER -d $POSTGRES_DB \
  -c "SELECT count(*) FROM pg_stat_activity WHERE datname = 'finsight';"

# 磁盘使用
docker system df
```

### 4.2 告警阈值建议

| 指标 | 警告 | 严重 |
|------|------|------|
| API 错误率 | > 1% | > 5% |
| P95 响应时间 | > 200ms | > 500ms |
| 磁盘使用率 | > 70% | > 90% |
| DB 连接数 | > 50 | > 80 |

---

## 5. 未涵盖项（生产部署时补充）

| 项目 | 说明 |
|------|------|
| 异地备份 | 将 dump 文件同步到 S3/OSS（不在本阶段范围） |
| PITR（时间点恢复） | 需 WAL 归档配置（生产高可用要求） |
| 监控集成 | Prometheus/Grafana 告警规则（见 PHASE8_OBSERVABILITY_CHECKLIST.md） |
