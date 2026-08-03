# Phase 7 Compose 配置验证报告

**日期**: 2026-06-08  
**状态**: ✅ **Compose config 验证通过 | Docker daemon 未运行（环境限制）**

---

## 验证命令与结果

### 1. 基础配置（生产模式）

```bash
docker compose --env-file /tmp/env_smoke.env config --quiet
```

**结果**: ✅ exit 0 — 配置解析成功

### 2. Dev 模式叠加

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml --env-file /tmp/env_smoke.env config --quiet
```

**结果**: ✅ exit 0 — 配置解析成功

### 3. Smoke 模式叠加

```bash
docker compose -f docker-compose.yml -f docker-compose.smoke.yml --env-file /tmp/env_smoke.env config --quiet
```

**结果**: ✅ exit 0 — 配置解析成功

---

## 占位 env 说明

验证时使用以下占位 env（非真实密钥）：

```
POSTGRES_DB=finsight_smoke
POSTGRES_USER=finsight_smoke
POSTGRES_PASSWORD=smoke_placeholder_pass
JWT_SECRET=smoke_placeholder_jwt_secret_64chars_xxxxxxxxxxxxxxxxxxxxxxxxxx
API_AUTH_KEYS=smoke_placeholder_api_key
OPENAI_COMPATIBLE_API_KEY=<OPENAI_COMPATIBLE_API_KEY>
OPENAI_COMPATIBLE_API_BASE=https://example.invalid/v1
OPENAI_COMPATIBLE_MODEL=gpt-4o-mini
```

---

## Docker Daemon 状态

| 检查项 | 结果 |
|--------|------|
| Docker CLI 安装 | ✅ version 29.4.0 |
| Docker Compose | ✅ v5.1.2 |
| Docker Desktop daemon | ❌ 未运行（Windows named pipe 不存在） |
| 实际容器启动 | ❌ 受 daemon 未运行限制 |

**环境说明**: 当前运行环境中 Docker Desktop 的 Linux engine 未启动（`npipe:////./pipe/dockerDesktopLinuxEngine` 不存在）。Compose config 解析（不需要 daemon）全部通过，但实际容器构建和运行无法执行。

**结论**: Compose 文件语法 ✅，实际 smoke 容器验证需在 Docker daemon 已启动的环境中执行。

---

## Compose 文件检查摘要

### docker-compose.yml

| 检查项 | 结果 |
|--------|------|
| 必需变量用 `${VAR:?msg}` 语法声明 | ✅ |
| postgres/backend/frontend 三服务 | ✅ |
| backend depends_on postgres healthy | ✅ |
| frontend depends_on backend healthy | ✅ |
| healthcheck 配置完整 | ✅ |
| volumes 使用命名卷 | ✅ |
| backend/postgres 仅 expose（不暴露到主机） | ✅ |
| frontend 暴露 :80 | ✅ |

### docker-compose.dev.yml

| 检查项 | 结果 |
|--------|------|
| DEV_MODE=1 | ✅ |
| postgres 暴露 5432 到主机 | ✅ |
| backend 暴露 8000 到主机 | ✅ |
| frontend 端口 5174:80 | ✅ |

### docker-compose.smoke.yml

| 检查项 | 结果 |
|--------|------|
| 独立容器名（finsight-smoke-*）避免冲突 | ✅ |
| 独立 volume 名（finsight_smoke_*）避免冲突 | ✅ |
| DEV_MODE=1 | ✅ |
| RAG_EMBEDDING=hash 跳过模型下载 | ✅ |
| frontend 暴露 18080:80（避开生产 :80） | ✅ |
| `ports: !override` 正确覆盖默认端口 | ✅ |

---

## 风险提示

1. **model_cache 卷 (~2GB)**: docker-compose.yml 注释中说明 model_cache 持久化 BGE-M3/reranker 权重。smoke.yml 使用独立 `finsight_smoke_model_cache`，但 smoke 模式通过 `RAG_EMBEDDING=hash` 绕过了模型加载，该卷实际不会下载权重。
2. **down 操作**: `docker compose down` 保留 volumes，`down -v` 删除 volumes。smoke 专用卷可用 `down -v` 清理，但必须使用 `-f docker-compose.smoke.yml` 指定，避免误删生产 `finsight_postgres_data`。

---

## 建议操作

在 Docker daemon 可用的环境中，执行以下步骤完成真实 smoke 验证：

```bash
# 1. 启动 smoke 环境
docker compose -f docker-compose.yml -f docker-compose.smoke.yml --env-file .env.server up -d --build

# 2. 等待服务健康
docker compose -f docker-compose.yml -f docker-compose.smoke.yml ps

# 3. 验证健康接口
curl http://localhost:18080/health

# 4. 验证前端
curl http://localhost:18080/

# 5. 关闭 smoke 环境（保留 volumes）
docker compose -f docker-compose.yml -f docker-compose.smoke.yml down

# 6. 可选：清理 smoke 专用卷
docker compose -f docker-compose.yml -f docker-compose.smoke.yml down -v
```
