# FinSight 部署指南

本文件覆盖：**端口暴露策略** + **环境变量分类** + **常见部署形态**。完整的变量清单见仓库根 `.env.example`（开发模板）与 `.env.server.example`（Docker / 生产模板）。

---

## 一、端口暴露策略

### 生产默认

`docker-compose.yml` 面向生产安全默认值：

- 仅 `frontend` 服务向宿主机暴露 `80:80`，由前端 Nginx 反向代理 `/api`、`/chat`、`/health` 到后端。
- `backend:8000` 只在 Compose 内网通过 `expose` 给反向代理访问，不映射到宿主机。
- `postgres:5432` 只在 Compose 内网通过 service name `postgres` 访问，不映射到宿主机。
- 所有生产必填变量通过 `.env.server` 或部署平台注入；缺失时 Compose 或后端启动会 fail-fast。

### 本地开发（Docker Compose）

Compose 会自动加载名为 `docker-compose.override.yml` 的文件。为避免误把开发端口暴露规则带入默认 `docker compose up`，仓库使用显式文件：

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

`docker-compose.dev.yml` 仅用于本地：

- 暴露 `postgres` 到 `localhost:5432`；
- 暴露 `backend` 到 `localhost:8000`；
- 暴露 `frontend` 到 `localhost:5174`；
- 设置 `DEV_MODE=1`，允许本地无正式认证服务运行。

生产环境禁止使用 `docker-compose.dev.yml`。

### 本地隔离 Smoke（不碰默认卷）

默认 `docker-compose.yml` 使用固定容器名与命名卷。若本机已经有 FinSight 实例或历史数据卷，直接 `up/down -v` 可能影响本地数据。仓库提供隔离覆盖文件用于 smoke：

```bash
docker compose -f docker-compose.yml -f docker-compose.smoke.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.smoke.yml up -d --build
curl http://localhost:18080/health
docker compose -f docker-compose.yml -f docker-compose.smoke.yml down
```

`docker-compose.smoke.yml` 使用独立容器名、独立网络、独立命名卷，并把前端映射到 `localhost:18080`。如需删除 smoke 生成的数据卷，必须确认卷名为 `finsight_smoke_*` 后再清理。

注意：该文件使用 Compose 的 `!override` 标签覆盖默认 `80:80` 端口映射；如果本机 Compose 版本过旧导致解析失败，请升级 Docker Compose v2 后再跑 smoke。

---

## 二、三类部署环境变量

FinSight 有三种典型部署形态，对应不同的 env 文件。**所有变量定义在 `.env.example` / `.env.server.example` 中保持单一来源**，本节给出"哪种部署用哪个文件 + 哪些变量必填"的对照。

| 部署形态 | 启动方式 | 主 env 文件 | DEV_MODE | 必填项 |
|---|---|---|---|---|
| **本机开发**（最常用） | `npm run dev` + `uvicorn`（前后端分别跑） | `.env`（复制自 `.env.example`） | `=1` | 至少 1 个 LLM key（OpenAI 兼容或 Gemini Proxy） |
| **本地 Docker** | `docker compose -f docker-compose.yml -f docker-compose.dev.yml up` | `.env.server`（复制自 `.env.server.example`） | `=1` | 同上 + Postgres 用户/密码（compose 内置） |
| **本地隔离 Smoke** | `docker compose -f docker-compose.yml -f docker-compose.smoke.yml up` | 临时 shell env 或 `.env.server` | `=1` | CI 同款占位变量即可验证构建/代理/健康检查 |
| **生产** | `docker compose -f docker-compose.yml up`（不带 `dev.yml`） | `.env.server`（部署平台注入） | **不设或 `=0`** | 完整：LLM + Postgres + JWT_SECRET + API_AUTH_KEYS + 财经 API key + SMTP（如启用告警） |

### 必填变量速查

无论哪种部署，下列变量缺失会让后端 fail-fast：

| 变量 | 用途 | 备注 |
|---|---|---|
| `OPENAI_COMPATIBLE_API_KEY` + `OPENAI_COMPATIBLE_API_BASE` + `OPENAI_COMPATIBLE_MODEL` | 主 LLM | 也可通过 `GEMINI_PROXY_*` 替代 |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | RAG v2 + LangGraph checkpoints | 仅在 `LANGGRAPH_CHECKPOINTER_BACKEND=postgres` 或 `RAG_V2_BACKEND=postgres` 时必填 |
| `JWT_SECRET` | 生产签发 token 用 | 仅生产必填（DEV_MODE=1 可空） |
| `API_AUTH_KEYS` | 内部 API key 列表（逗号分隔） | 仅生产必填 |

### 可选但推荐启用的变量

| 类别 | 变量 | 说明 |
|---|---|---|
| 财经数据 | `FMP_API_KEY` / `FINNHUB_API_KEY` / `ALPHA_VANTAGE_API_KEY` / `TWELVE_DATA_API_KEY` / `MARKETSTACK_API_KEY` / `EODHD_API_KEY` | 11 源价格瀑布的中间层；不配会自动降级到 yfinance |
| 搜索 | `TAVILY_API_KEY` / `EXA_API_KEY` | DeepSearch Agent 主路径；不配会降级到 DuckDuckGo |
| 宏观 | `FRED_API_KEY` | MacroAgent；不配只能用网络新闻替代 |
| 监控 | `LANGFUSE_*` / `LANGSMITH_*` | Trace 与链路观测；不配不影响功能 |
| 邮件 | `SMTP_SERVER` / `SMTP_USER` / `SMTP_PASSWORD` / `EMAIL_FROM` | Alerts 邮件发送；不配则 Alerts 仅入库不发邮件 |
| Supabase | `SUPABASE_URL` / `SUPABASE_PUBLISHABLE_KEY` / `VITE_SUPABASE_*` | Magic Link 登录；不配可走匿名模式 |

### 前端运行时变量（仅识别 `VITE_*` 前缀）

| 变量 | 用途 | 默认值 |
|---|---|---|
| `VITE_API_BASE_URL` | 后端 API base | `http://127.0.0.1:8000` |
| `VITE_SUPABASE_URL` / `VITE_SUPABASE_PUBLISHABLE_KEY` | Supabase Auth | 空 |
| `VITE_RAG_INSPECTOR_DEV_*` | 本地 dev auth 进入 RAG Inspector | **禁止在生产启用** |

### 仅开发模板（`.env.example`）独有

- `DEV_MODE=1` — 关闭生产 fail-fast
- `RAG_OBSERVABILITY_DEV_*` — 本地 dev auth 写入端（与 `VITE_RAG_INSPECTOR_DEV_*` 配对）
- `LANGGRAPH_PLANNER_AB_*` — Planner A/B 实验开关
- `LANGGRAPH_AGENT_TEMPERATURE` / `LANGGRAPH_PLANNER_TEMPERATURE` / `LANGGRAPH_SYNTHESIZE_TEMPERATURE` — 各 LLM 节点温度
- `LANGGRAPH_PLANNER_MODE=stub` / `LANGGRAPH_SYNTHESIZE_MODE=stub` — 本地 dry-run 默认（避免无 key 时报错）
- `PRICE_CB_*` / `NEWS_CB_*` — Circuit breaker 阈值
- `BUDGET_MAX_*` — 单次执行预算上限
- `CACHE_JITTER_RATIO` / `CACHE_NEGATIVE_TTL` — 缓存控制
- `API_PUBLIC_PATHS` — 不需要鉴权的公开路径列表

### 仅服务器模板（`.env.server.example`）独有

- `LANGGRAPH_PLANNER_MODE=llm` / `LANGGRAPH_SYNTHESIZE_MODE=narrative` / `LANGGRAPH_EXECUTE_LIVE_TOOLS=true` — 生产默认值
- `LLM_ENDPOINT_DEFAULT_COOLDOWN_SEC` / `DEEPSEARCH_LLM_TOKEN_TIMEOUT_SECONDS` / `LANGGRAPH_DEEP_SEARCH_AGENT_TIMEOUT_SECONDS` — 生产 LLM 超时配置
- `LLM_API_KEY` / `LLM_API_BASE` / `EVAL_LLM_MODEL` — RAG quality eval 专用 LLM（仅测试运行需要）
- `RAG_OBSERVABILITY_AUTH_CACHE_SECONDS` — Supabase 身份缓存秒数

---

## 三、变量审计清单（2026-05-13 整理）

- ✅ 已移除：`USE_SCHEMA_ROUTER`（SchemaToolRouter 已退役，参见 `CHANGELOG.md` Unreleased 段）。
- ✅ 已对齐：`.env.example` 与 `.env.server.example` 主要 LLM / 财经 API / RAG / Embedding 变量同名同义。
- 🟡 重复但合理（无需合并）：Postgres / SMTP / Supabase 等变量在两个文件中都存在，因为本地开发也可能需要走 Docker。
- 🟠 待清理（后续可做）：`MASSIVE_API_KEY` 在两个文件都列了，但代码中**未见生产引用**——保留但标注"待核实"。

---

## 四、首次部署 Checklist

1. 复制：`cp .env.server.example .env.server`
2. 强制替换所有 `REPLACE_ME` 占位符；`.env.server.example` 中包含 LLM、行情源、搜索、监控、SMTP 等多类占位符，生产前必须逐项确认是否填入真实值或显式留空关闭对应能力。
3. 选择数据库后端：
   - 默认（SQLite，单机）：保持 `LANGGRAPH_CHECKPOINTER_BACKEND=sqlite` 与 `RAG_V2_BACKEND=auto`。
   - PostgreSQL（推荐生产）：在 docker-compose 中已配置；只需确保 `POSTGRES_PASSWORD` 强密码。
4. 配置 LLM：至少 1 个 OpenAI 兼容端点或 Gemini Proxy；建议至少 2 个 + endpoint round-robin（`LLM_RATE_LIMIT_RETRY_*`）。
5. 配置认证：生产必须 `DEV_MODE=` 不设；`API_AUTH_KEYS` 列表用于内部服务调用；Supabase 用于终端用户登录。
6. 启动：`docker compose -f docker-compose.yml up -d`。
7. 验证：`curl http://<host>/health` 返回 `200`；`curl http://<host>/api/personas` 返回 4 个 Persona。

---

## 五、问题排查

| 现象 | 可能原因 | 处理 |
|---|---|---|
| `docker compose up` 后端立即退出 | 缺生产必填变量 | 检查 `.env.server` 是否所有 `REPLACE_ME` 都替换；查看后端日志 `docker compose logs backend` |
| `/chat/supervisor` 返回 500 | LLM key 失效或 endpoint 不可达 | 查看 `LANGGRAPH_*` 配置；在 `/internal/health` 端点查看组件状态（需 admin 身份） |
| 标的研究页显示 `数据暂不可用` | 财经 API key 未配，`/api/dashboard*` 兼容数据层降级 | 配 `FMP_API_KEY` / `FINNHUB_API_KEY` 中任一 |
| Alerts 创建成功但收不到邮件 | SMTP 未配 | 设 `SMTP_*` 系列；不配只能保存订阅不发邮件 |
| RAG Inspector 跳回 `/welcome` | 匿名用户被 `AuthenticatedGuard` 拦截 | 配 Supabase 或本地启用 dev auth（仅开发） |

---

## 六、Release Gate（上线前一键门禁）

仓库提供 `scripts/release_gate.ps1`（Windows / PowerShell）与 `scripts/release_gate.sh`（POSIX）串起后端 + 前端的所有上线必通检查。

涵盖步骤：

| 步骤 | 内容 |
|---|---|
| `backend.import-smoke` | 用 FastAPI `TestClient` 启动 lifespan,GET `/health` 必须返回 200 (设 `DEV_MODE=true` 跳过生产 env 校验) |
| `backend.pytest-core` | `pytest backend/tests` (默认), 加 `-All` 同时跑 `tests/` 顶层 |
| `vue.lint` | `npm run lint` 0 errors / 0 warnings |
| `vue.typecheck` | `vue-tsc --noEmit` 必须通过 |
| `vue.build` | Vue 生产构建 |

用法：

```powershell
# 默认全套(backend/tests + 前端 4 件套)
pwsh scripts/release_gate.ps1

# 只跑 smoke + Vue build (CI 拉新分支时用)
pwsh scripts/release_gate.ps1 -SmokeOnly

# 同时跑 tests/ 顶层全量(发布前 release 候选用)
pwsh scripts/release_gate.ps1 -All

# 跳过某一侧
pwsh scripts/release_gate.ps1 -SkipFrontend
pwsh scripts/release_gate.ps1 -SkipBackend
```

退出码 = 失败步骤数,0 表示全部通过。CI 集成时直接使用退出码判定。

`-WithE2E` 模式: 在 Vue lint/typecheck/build 之后追加 `npm run test:e2e`。Vite dev server 自动启动,所有后端 API 都应走 Python FastAPI 或测试 mock。

---

## 七、Plan 门控 (Feature Gate)

后端三个关键端点已通过 `backend/services/entitlements.py` 注入 Plan 门控:

| 端点 | 检查的 feature | 拒绝时返回 |
|---|---|---|
| `POST /chat/supervisor` (output_mode=investment_report) | `deep_research` | 403 `plan_feature_required` |
| `POST /chat/supervisor/stream` (同上) | `deep_research` | 403 `plan_feature_required` |
| `POST /api/export/pdf` | `export_pdf` | 403 `plan_feature_required` |

**结构化错误:** 403/429 响应 body 形如:
```json
{
  "detail": {
    "code": "plan_feature_required",
    "feature": "deep_research",
    "plan": "free",
    "message": "Your free plan does not include 'deep_research'. Upgrade to unlock."
  }
}
```

**Plan 配置:** `data/user_plans.json` 按 user_id 存档。admin role 自动映射 admin plan (无视配置文件)。新功能要做 Plan 门控时,在 `entitlements.py::PLAN_FEATURES` dict 中增加键 + 在路由端点添加一行 `enforce_feature(getattr(http_request.state, "principal", None), "<feature_name>")` 即可。

**前端现状:** 当前 7 入口前端不再接入套餐页、PlanBadge 或全局 UpgradeModal；商业化 UX 暂不属于当前主线。若未来恢复计费体验，需要重新设计入口、文案和升级弹窗，而不是假设旧空壳仍存在。

**Usage 查询端点:** `GET /api/me/entitlements` 返回 plan + features + limits + **usage** 一站式；`GET /api/me/usage` 轻量端点（仅 usage）；`GET /api/plans` 公开列出所有 plan 的功能与配额。当前这些接口保留为后端能力，不作为当前前端主导航体验。
