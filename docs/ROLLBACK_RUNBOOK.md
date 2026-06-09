# 回滚运维手册

**文档版本**：1.0  
**适用版本**：FinSight v0.8+  
**最后更新**：2026-06-09

---

## 1. 回滚策略概述

FinSight 采用镜像标签回滚策略：每次发布前保留前一版本镜像，回滚时切换镜像标签 + 还原数据库（如有 schema 变更）。

| 回滚类型 | 适用场景 | 预计耗时 |
|---------|---------|---------|
| 快速回滚（镜像切换） | 无 schema 变更，仅代码回归 | 2-5 分钟 |
| 完整回滚（镜像 + DB） | schema 变更导致的问题 | 10-20 分钟 |
| 紧急回滚（强制重启） | 容器崩溃循环 | 1-2 分钟 |

---

## 2. 发布前准备（回滚前提）

每次发布前必须执行：

```bash
# 1. 标记当前镜像为 previous
docker tag finsight-backend:latest finsight-backend:previous
docker tag finsight-frontend:latest finsight-frontend:previous

# 2. 记录当前 DB schema 版本
docker exec finsight-postgres psql -U $POSTGRES_USER -d $POSTGRES_DB \
  -c "SELECT version, applied_at FROM schema_migrations ORDER BY applied_at DESC LIMIT 5;"

# 3. 执行全量 DB 备份（参见 BACKUP_RESTORE_RUNBOOK.md）
bash scripts/backup.sh

echo "[PRE_DEPLOY] Previous image tagged, DB backed up. Ready to deploy."
```

---

## 3. 快速回滚（代码回滚，无 DB 变更）

适用：部署后发现功能回归、性能劣化，但无数据库 schema 变更。

```bash
#!/bin/bash
# 快速回滚脚本

set -e

echo "[ROLLBACK] Starting quick rollback at $(date)"

# 1. 停止当前版本
docker compose stop backend frontend

# 2. 切换到 previous 镜像
# 编辑 docker-compose.override.yml 或使用环境变量
export BACKEND_IMAGE="finsight-backend:previous"
export FRONTEND_IMAGE="finsight-frontend:previous"

# 3. 重启
docker compose up -d backend frontend

# 4. 等待健康检查
echo "[ROLLBACK] Waiting for services to become healthy..."
for i in {1..30}; do
  status=$(docker inspect --format='{{.State.Health.Status}}' finsight-backend 2>/dev/null)
  if [ "$status" = "healthy" ]; then
    echo "[ROLLBACK] Backend healthy after ${i}s"
    break
  fi
  sleep 1
done

# 5. 验证
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/health)
if [ "$HTTP_STATUS" = "200" ]; then
  echo "[ROLLBACK] SUCCESS — /api/health returned 200"
else
  echo "[ROLLBACK] FAILED — /api/health returned $HTTP_STATUS"
  exit 1
fi
```

---

## 4. 完整回滚（代码 + DB 回滚）

适用：schema 变更导致数据不一致或功能中断。

```bash
#!/bin/bash
# 完整回滚脚本（危险操作，需人工确认）

set -e

BACKUP_FILE="${1:-}"
if [ -z "$BACKUP_FILE" ]; then
  echo "Usage: $0 <backup_file.dump>"
  echo "Available backups:"
  ls -la backups/*.dump 2>/dev/null || echo "  No backups found"
  exit 1
fi

read -p "[ROLLBACK] This will RESTORE DB from $BACKUP_FILE. Continue? [yes/no] " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
  echo "Aborted."
  exit 0
fi

echo "[ROLLBACK] Starting full rollback at $(date)"

# 1. 停止所有服务
docker compose stop backend frontend

# 2. 恢复数据库
echo "[ROLLBACK] Restoring database from $BACKUP_FILE..."
docker exec -i finsight-postgres psql -U $POSTGRES_USER \
  -c "DROP DATABASE IF EXISTS finsight_rollback_tmp;"
docker exec -i finsight-postgres psql -U $POSTGRES_USER \
  -c "CREATE DATABASE finsight_rollback_tmp;"
docker exec -i finsight-postgres pg_restore \
  -U $POSTGRES_USER -d finsight_rollback_tmp < "$BACKUP_FILE"
docker exec -i finsight-postgres psql -U $POSTGRES_USER \
  -c "DROP DATABASE finsight; ALTER DATABASE finsight_rollback_tmp RENAME TO finsight;"

# 3. 切换镜像
export BACKEND_IMAGE="finsight-backend:previous"
export FRONTEND_IMAGE="finsight-frontend:previous"
docker compose up -d backend frontend

# 4. 验证
sleep 5
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/health)
echo "[ROLLBACK] Health check: $HTTP_STATUS"

echo "[ROLLBACK] COMPLETE at $(date)"
```

---

## 5. 紧急回滚（容器崩溃循环）

适用：容器不断 restart，无法等待正常回滚流程。

```bash
# 强制停止并重建（使用 previous 镜像）
docker rm -f finsight-backend
docker run -d \
  --name finsight-backend \
  --network finsight-net \
  --env-file .env.server \
  finsight-backend:previous

# 检查日志
docker logs --tail=50 finsight-backend
```

---

## 6. 回滚决策矩阵

| 观测到的问题 | 建议回滚类型 | 检查项 |
|------------|------------|--------|
| API 500 错误率 > 5% | 快速回滚 | 无 schema 变更则优先快速 |
| P95 延迟 > 500ms | 快速回滚 | 查看 DB 查询是否有慢查询 |
| 数据损坏 / 乱码 | 完整回滚 | 先停止写入，再恢复 |
| 容器启动失败 | 紧急回滚 | `docker logs` 确认原因 |
| 前端白屏 | 快速回滚（仅 frontend） | 可只回滚 frontend 镜像 |

---

## 7. 回滚后验证清单

- [ ] `/api/health` 返回 200
- [ ] `/api/portfolio/summary` 返回 200
- [ ] `/api/today` 返回 200
- [ ] 前端首页可访问（HTTP 200）
- [ ] 前端登录/会话正常
- [ ] 查看 `docker logs finsight-backend` 无异常 ERROR
- [ ] 通知相关方回滚完成，记录回滚日志

---

## 8. 注意事项

1. **不执行 `docker compose down -v`**：会删除数据卷（含数据库），不可恢复。
2. **回滚前先备份当前状态**：即使当前版本有问题，其数据可能仍然有价值。
3. **schema 降级风险**：如新版本已向数据库写入新格式数据，回滚后旧代码可能无法正确读取。回滚前评估数据兼容性。
4. **环境变量**：切换镜像不会自动切换 `.env.server`，如配置也有变更需同步回滚。
