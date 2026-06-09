# 备份与恢复运维手册

**文档版本**：1.0  
**适用版本**：FinSight v0.8+  
**最后更新**：2026-06-09

---

## 1. 备份架构

FinSight 的持久化数据分为两层：

| 层 | 存储位置 | 备份方式 |
|----|---------|---------|
| **结构化数据** | PostgreSQL（含 pgvector） | pg_dump / 物理备份 |
| **文件数据** | 本地文件系统（笔记图片、报告文件） | rsync / tar |
| **环境配置** | `.env.server` | 手动备份（加密） |

---

## 2. 数据库备份

### 2.1 逻辑备份（推荐用于迁移）

```bash
# 全库备份（自定义格式，支持并行恢复）
pg_dump -h localhost -U finsight -d finsight \
  --format=custom --compress=9 \
  --file=backups/finsight_$(date +%Y%m%d_%H%M%S).dump

# Docker 环境下执行
docker exec finsight-postgres pg_dump \
  -U $POSTGRES_USER -d $POSTGRES_DB \
  --format=custom --compress=9 \
  > backups/finsight_$(date +%Y%m%d_%H%M%S).dump
```

### 2.2 物理备份（推荐用于 PITR）

```bash
# 停机备份（确保一致性）
docker compose stop backend
docker exec finsight-postgres pg_basebackup \
  -U postgres -D /tmp/basebackup -Fp -Xs -P
docker cp finsight-postgres:/tmp/basebackup ./backups/basebackup_$(date +%Y%m%d)
docker compose start backend
```

### 2.3 备份验证

```bash
# 验证备份文件完整性
pg_restore --list backups/finsight_*.dump | head -20

# 恢复到测试数据库验证
createdb finsight_verify
pg_restore -d finsight_verify backups/finsight_latest.dump
psql -d finsight_verify -c "SELECT COUNT(*) FROM watchlist_meta;"
dropdb finsight_verify
```

---

## 3. 文件数据备份

### 3.1 笔记图片

```bash
# 图片存储路径（对应 UPLOAD_DIR 环境变量）
UPLOAD_DIR="${UPLOAD_DIR:-./uploads}"

# 增量备份
rsync -av --delete "$UPLOAD_DIR/" backups/uploads_$(date +%Y%m%d)/

# 压缩归档
tar -czf backups/uploads_$(date +%Y%m%d_%H%M%S).tar.gz "$UPLOAD_DIR/"
```

### 3.2 RAG 向量索引

```bash
# pgvector 数据已包含在数据库备份中
# 额外备份本地模型文件（不频繁变化）
tar -czf backups/models_$(date +%Y%m%d).tar.gz models/
```

---

## 4. 配置文件备份

```bash
# 加密备份（使用 GPG 或 openssl）
openssl enc -aes-256-cbc -pbkdf2 \
  -in .env.server -out backups/env_server_$(date +%Y%m%d).enc

# 解密
openssl enc -aes-256-cbc -pbkdf2 -d \
  -in backups/env_server_20260609.enc -out .env.server.restored
```

---

## 5. 数据库恢复

### 5.1 全量恢复

```bash
# 1. 停止后端
docker compose stop backend

# 2. 删除现有数据（确认后执行）
docker exec finsight-postgres psql -U $POSTGRES_USER \
  -c "DROP DATABASE IF EXISTS finsight; CREATE DATABASE finsight;"

# 3. 恢复
docker exec -i finsight-postgres pg_restore \
  -U $POSTGRES_USER -d finsight < backups/finsight_target.dump

# 4. 重启后端
docker compose start backend

# 5. 验证
curl http://localhost:8000/api/health
```

### 5.2 单表恢复

```bash
# 仅恢复 watchlist_meta 表
pg_restore -t watchlist_meta \
  -U $POSTGRES_USER -d finsight backups/finsight_target.dump
```

---

## 6. 文件数据恢复

```bash
# 恢复上传文件
mkdir -p "$UPLOAD_DIR"
tar -xzf backups/uploads_20260609_120000.tar.gz -C ./

# 或从 rsync 备份恢复
rsync -av backups/uploads_20260609/ "$UPLOAD_DIR/"
```

---

## 7. 自动化备份脚本

```bash
#!/bin/bash
# scripts/backup.sh — 每日 02:00 由 cron 调用

set -e

BACKUP_DIR="./backups"
RETENTION_DAYS=30
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting backup..."

# DB backup
docker exec finsight-postgres pg_dump \
  -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  --format=custom --compress=9 \
  > "$BACKUP_DIR/db_${TIMESTAMP}.dump"

# File backup
tar -czf "$BACKUP_DIR/uploads_${TIMESTAMP}.tar.gz" \
  "${UPLOAD_DIR:-./uploads}/" 2>/dev/null || true

# Cleanup old backups
find "$BACKUP_DIR" -name "*.dump" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +$RETENTION_DAYS -delete

echo "[$(date)] Backup complete: db_${TIMESTAMP}.dump"
```

安装 cron：
```bash
# 每天 02:00 执行
echo "0 2 * * * cd /opt/finsight && bash scripts/backup.sh >> logs/backup.log 2>&1" | crontab -
```

---

## 8. 备份清单（每次上线前）

- [ ] 执行全量 DB 备份并验证文件大小 > 0
- [ ] 执行 `pg_restore --list` 验证备份可读
- [ ] 备份 `.env.server`（加密存储）
- [ ] 备份 `uploads/` 目录
- [ ] 记录备份文件路径到值班日志
