# Phase 7 Docker Smoke 报告

**日期**: 2026-06-08  
**状态**: ⚠️ **环境限制 — Docker daemon 未运行，compose up 无法执行**

---

## 环境限制说明

| 组件 | 状态 |
|------|------|
| Docker CLI 版本 | 29.4.0 ✅ |
| Docker Compose 版本 | v5.1.2 ✅ |
| Docker Desktop Linux Engine | ❌ 未运行 |
| Compose config 解析 | ✅ 全部通过 |
| 实际 `docker compose up` | ❌ 无法执行 |

错误信息：
```
failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine;
check if the path is correct and if the daemon is running
```

---

## 替代验证：本地 uvicorn + Python（已通过）

由于 Docker daemon 不可用，Phase 7 采用本地 Python uvicorn 进行等效验证：

### 启动命令

```bash
DEV_MODE=1 uvicorn backend.api.main:app --host 127.0.0.1 --port 8001 --log-level warning
```

### 启动日志关键行

```
[INFO] [Init] Core tools imported successfully.
[INFO] [Init] Chart detector imported successfully.
[INFO] [Init] MemoryService initialized successfully.
[WARNING] DEV_MODE ON — auth bypassed and rate limits disabled.
[INFO] [Scheduler] PRICE_ALERT_SCHEDULER_ENABLED is false; skip start.
[INFO] [GraphRunner] initialized in lifespan
```

### /health 响应

```json
{"status":"ok","version":"1.0.0","uptime_seconds":3,"timestamp":"2026-06-08T14:14:10Z"}
```

---

## API 关键接口验证（12/12 通过）

| 接口 | 状态码 | 结果 |
|------|--------|------|
| GET /health | 200 | ✅ |
| GET /api/me | 200 | ✅ |
| GET /api/today | 200 | ✅ |
| GET /api/research-quality | 200 | ✅ (修复后) |
| GET /api/what-changed | 200 | ✅ (修复后) |
| GET /api/research-notes | 200 | ✅ |
| GET /api/portfolio/summary | 200 | ✅ |
| GET /api/portfolio/risk-lens | 200 | ✅ |
| GET /api/user/watchlist | 200 | ✅ |
| GET /api/reports/index | 200 | ✅ |
| GET /api/timeline/AAPL | 200 | ✅ |
| GET /api/alerts/feed | 200 | ✅ |

---

## 文件系统验证

### Notes 图片上传

| 操作 | 状态 |
|------|------|
| 创建 note | ✅ 200 |
| 上传 PNG 图片 | ✅ 200，返回 `/api/notes/images/...` URL |
| 通过 URL 访问图片 | ✅ 200，Content-Type: image/png |
| 路径遍历防护 `../../etc/passwd` | ✅ 404 拦截 |
| 路径遍历防护 URL 编码 `%2e%2e` | ✅ 404 拦截 |

### SQLite 初始化

- `backend_data/` 下 SQLite 文件自动创建
- Session / portfolio / watchlist / notes 数据可读写

---

## 已发现并修复的 Bug

### Bug: `require_matching_identity` 调用方式不兼容

**影响路由**: `/api/research-quality` + `/api/what-changed`

**症状**: HTTP 500 `TypeError: require_matching_identity() takes 0 positional arguments but 3 were given`

**根因**: `backend/security/auth.py` 中函数签名已改为 keyword-only，但两个路由还用旧的位置参数调用

**修复**:
```python
# 修复前（错误）
require_matching_identity(current_user, user_id, session_id)

# 修复后（正确）
require_matching_identity(
    principal=current_user,
    provided=session_id,
    expected=current_user.session_id,
    field_name="session_id",
)
```

**文件**: `backend/api/research_quality_router.py` + `backend/api/what_changed_router.py`

---

## 后续：Docker Smoke 所需步骤

当 Docker Desktop 可用时，执行：

```bash
# 用 smoke 占位 env
docker compose -f docker-compose.yml -f docker-compose.smoke.yml \
  --env-file .env.server up -d --build

# 等待约 2-3 分钟（包含 BGE-M3 加载或 hash embedding 模式跳过）
curl http://localhost:18080/health
curl http://localhost:18080/

# 清理
docker compose -f docker-compose.yml -f docker-compose.smoke.yml down
```

**预期结果**：基于本地验证全通过，Docker smoke 预计也能通过，唯一变量是容器网络和 postgres 初始化时序。
