# PHASE8_DOCKER_SMOKE_REPORT.md

**生成时间**：2026-06-09  
**阶段**：Phase 8 — Docker 隔离 Smoke 验证  
**结论**：PASS（12/12 端点通过，数据读写完整闭环）

---

## 1. 镜像构建策略

因当前网络无法访问 Docker Hub（`registry-1.docker.io` 返回 EOF），采用本地已有基础镜像分层 build：

| 镜像 | 基础镜像 | 额外操作 |
|------|---------|---------|
| `finsight-smoke-backend:updated` | `finsight-main-backend:latest` | COPY 最新代码 + `pip install python-multipart` |
| `finsight-smoke-frontend:updated` | `finsight-main-frontend:latest` | COPY 当前 `frontend-vue/dist/` |
| postgres | `pgvector/pgvector:pg16`（已在本地） | 无修改 |

**`python-multipart` 补装原因**：旧基础镜像构建于 Phase 4 文件上传功能落地之前，缺少该依赖；FastAPI 启动时报 `RuntimeError: Form data requires "python-multipart"`，需手动补装。

---

## 2. Smoke 环境配置

| 配置项 | 值 |
|--------|---|
| Compose 文件 | `docker-compose.yml` + `docker-compose.smoke.yml` |
| 端口映射 | 18080:80（frontend nginx 代理） |
| DEV_MODE | 1（auth 旁路，user_id 固定为 `default_user`） |
| RAG_EMBEDDING | hash（跳过 BGE-M3 下载） |
| JWT_SECRET | GUID 随机生成（非生产值） |
| API_AUTH_KEYS | GUID 随机生成（非生产值） |
| 卷名 | `finsight_smoke_*`（独立命名空间） |

---

## 3. 容器健康状态

| 容器 | 状态 | 说明 |
|------|------|------|
| `finsight-smoke-postgres` | ✅ healthy | pg_isready 通过 |
| `finsight-smoke-backend` | ✅ healthy | `/api/health` 返回 200 |
| `finsight-smoke-frontend` | ✅ healthy | nginx + /api/ 代理正常 |

---

## 4. API Smoke 结果（通过 nginx 18080 代理）

### 4.1 只读端点（11/11）

| # | 端点 | 方法 | HTTP | 说明 |
|---|------|------|------|------|
| 1 | `/api/health` | GET | 200 | 健康检查 |
| 2 | `/api/portfolio/summary` | GET | 200 | 返回 positions 列表 |
| 3 | `/api/watchlist` | GET | 200 | 返回 watchlist 列表 |
| 4 | `/api/today` | GET | 200 | 聚合端点（6 模块） |
| 5 | `/api/what-changed` | GET | 200 | 变化摘要 |
| 6 | `/api/research-quality` | GET | 200 | 报告质量摘要 |
| 7 | `/api/reports` | GET | 200 | 报告列表 |
| 8 | `/api/alerts/feed` | GET | 200 | 告警 feed |
| 9 | `/api/morning-brief` | GET | 200 | 晨报 |
| 10 | `/api/research-notes` | GET | 200 | 笔记列表 |
| 11 | `/api/dashboard/news` | GET | 200 | 新闻 feed |

### 4.2 写入端点（4/4）

| # | 操作 | 路由 | 结果 | 读回验证 |
|---|------|------|------|---------|
| 1 | Watchlist 新增 | `POST /api/watchlist` | ✅ 200 | items=1 |
| 2 | Portfolio 写入 | `PUT /api/portfolio/positions/AAPL` | ✅ 200 | positions=1, live_price=301.54 |
| 3 | Note 创建 | `POST /api/research-notes` | ✅ 200 | note_id=note_4e93c6c27a97 |
| 4 | 图片上传 | `POST /api/research-notes/{id}/images` | ✅ 200 | URL 可访问，bytes=69 |

**注**：Portfolio `live_price=301.54` 表明行情工具桥（tools_bridge）在 DEV_MODE 下正常工作（返回模拟价格）。

---

## 5. 图片上传闭环验证

```
POST /api/research-notes/note_4e93c6c27a97/images
  → 200 {"url": "/api/notes/images/default_user/note_4e93c6c27a97/image_*.png"}

GET /api/notes/images/default_user/note_4e93c6c27a97/image_*.png
  → 200, Content-Length: 69 (有效 PNG)
```

使用标准 `multipart/form-data` 格式（Python `urllib.request` 构造，boundary `PhaseSmokeUpload8`）。

---

## 6. 已知非阻塞问题

| 问题 | 状态 | 说明 |
|------|------|------|
| BGE-M3 向量模型 | NOT_VERIFIED（环境限制） | smoke 使用 `RAG_EMBEDDING=hash` 跳过，生产部署需下载 |
| 外部行情 API key | 未配置 | tools_bridge 返回模拟数据（DEV_MODE） |

---

## 7. 清理

smoke 容器已停止并移除（`docker stop` + `docker rm`）；smoke 专用卷（`finsight_smoke_*`）保留，未执行 `down -v`。

**结论**：Docker 隔离 smoke 验证完整通过，所有 15 个 API 测试点（11 只读 + 4 写入）均成功，数据读写闭环验证完毕。
