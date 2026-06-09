# PHASE7 环境变量矩阵

## 概述

本文档覆盖 FinSight 的三个典型运行环境：

| 环境标识 | 启动方式 | 典型用途 |
|---|---|---|
| **local-dev** | `uvicorn` + `vite dev`，直接裸跑 | 日常开发、断点调试 |
| **local-docker** | `docker compose -f docker-compose.yml -f docker-compose.dev.yml up` | 本地全栈联调，端口暴露到宿主机 |
| **prod-like** | `docker compose -f docker-compose.yml up`（或 CI smoke：加 `docker-compose.smoke.yml`） | 类生产验证、正式部署 |

> **重要安全声明**：本文件中所有示例值均使用 `REPLACE_ME_xxx` 占位符，**切勿**将真实密钥提交到版本库。`.env` 文件已被 `.gitignore` 排除。

---

## 一、数据库（PostgreSQL）

| 变量名 | 必需级别 | local-dev 默认 | local-docker 默认 | prod-like | 用途 | 缺失行为 | 敏感 |
|---|---|---|---|---|---|---|---|
| `POSTGRES_DB` | **必需** | `finsight` | `finsight` | **必须显式设置** | 数据库名 | 后端启动失败 | 否 |
| `POSTGRES_USER` | **必需** | `finsight` | `finsight` | **必须显式设置** | 数据库用户名 | 后端启动失败 | 否 |
| `POSTGRES_PASSWORD` | **必需** | `REPLACE_ME_db_password` | `REPLACE_ME_db_password` | **必须显式设置** | 数据库密码 | 后端启动失败 | **是** |
| `RAG_V2_BACKEND` | 可选 | `auto`（自动检测） | compose 强制覆盖为 `postgres` | `postgres` | RAG 向量后端选择（auto / postgres / memory） | 降级为内存模式，重启后向量丢失 | 否 |

> **注意**：`docker-compose.yml` 在 `backend` service 的 `environment` 中对 `RAG_V2_BACKEND` 强制赋值为 `postgres`，覆盖 `.env` 中的任何设置。smoke 环境使用独立 volume `finsight_smoke_postgres_data`，不影响开发数据。

---

## 二、LLM（主力模型，OpenAI-Compatible 接口）

| 变量名 | 必需级别 | local-dev 默认 | local-docker 默认 | prod-like | 用途 | 缺失行为 | 敏感 |
|---|---|---|---|---|---|---|---|
| `OPENAI_COMPATIBLE_API_KEY` | **必需** | `REPLACE_ME_llm_api_key` | 同左，compose 强制校验 | **必须显式设置** | LLM 调用鉴权 Key | 后端启动失败 / 所有 AI 功能不可用 | **是** |
| `OPENAI_COMPATIBLE_API_BASE` | **必需** | `https://api.openai.com/v1` | 同左，compose 强制校验 | **必须显式设置** | LLM API Base URL | 后端启动失败 | 否 |
| `OPENAI_COMPATIBLE_MODEL` | **必需** | `gpt-4o-mini` | 同左，compose 强制校验 | **必须显式设置** | 默认模型名 | 后端启动失败 | 否 |
| `GEMINI_PROXY_API_KEY` | 可选 | 不设置 | 不设置 | 视需要 | Gemini 代理 Key（备用模型通道） | 相关功能静默跳过 | **是** |
| `GEMINI_PROXY_API_BASE` | 可选 | 不设置 | 不设置 | 视需要 | Gemini 代理 Base URL | 相关功能静默跳过 | 否 |
| `LANGGRAPH_PLANNER_MODE` | 可选 | `llm` | `llm` | `llm` | LangGraph 规划阶段模式（llm / mock） | 默认使用 LLM 模式 | 否 |
| `LANGGRAPH_SYNTHESIZE_MODE` | 可选 | `llm` | `llm` | `llm` | LangGraph 合成阶段模式（llm / mock） | 默认使用 LLM 模式 | 否 |
| `LANGGRAPH_EXECUTE_LIVE_TOOLS` | 可选 | `true` | `true` | `true` | 是否真实调用外部工具（true / false） | 默认 true，false 时走 mock | 否 |
| `DEV_MODE` | 可选 | `1`（dev 本地绕过） | docker-dev: `1`，prod: **不设置** | **不设置（或删除）** | 绕过部分鉴权与限速检查 | prod 若误设为 1 将跳过安全门控，**高危** | 否 |

---

## 三、金融数据 API

| 变量名 | 必需级别 | local-dev 默认 | local-docker 默认 | prod-like | 用途 | 缺失行为 | 敏感 |
|---|---|---|---|---|---|---|---|
| `ALPHA_VANTAGE_API_KEY` | 可选 | 不设置 | 不设置 | 推荐设置 | Alpha Vantage 行情/基本面数据 | 该数据源被跳过，降级为其他源 | **是** |
| `FINNHUB_API_KEY` | 可选 | 不设置 | 不设置 | 推荐设置 | Finnhub 实时行情、新闻 | 该数据源被跳过 | **是** |
| `TWELVE_DATA_API_KEY` | 可选 | 不设置 | 不设置 | 推荐设置 | Twelve Data 技术指标/时序数据 | 该数据源被跳过 | **是** |
| `FMP_API_KEY` | 可选 | 不设置 | 不设置 | 推荐设置 | Financial Modeling Prep 财报/估值 | 该数据源被跳过 | **是** |
| `OPENFIGI_API_KEY` | 可选 | 不设置 | 不设置 | 可选 | OpenFIGI 证券标识符映射 | 该数据源被跳过 | **是** |
| `EODHD_API_KEY` | 可选 | 不设置 | 不设置 | 可选 | EOD Historical Data 历史行情 | 该数据源被跳过 | **是** |
| `FRED_API_KEY` | 可选 | 不设置 | 不设置 | 可选 | FRED 宏观经济数据（美联储） | 该数据源被跳过 | **是** |

> 行情 API Key 均为可选，后端通过 multi-source fallback 降级，但覆盖源越多数据质量越好。

---

## 四、搜索 API

| 变量名 | 必需级别 | local-dev 默认 | local-docker 默认 | prod-like | 用途 | 缺失行为 | 敏感 |
|---|---|---|---|---|---|---|---|
| `TAVILY_API_KEY` | 可选 | 不设置 | 不设置 | 推荐设置 | Tavily 网络搜索（深度研究功能） | 深度研究功能不可用或降级 | **是** |
| `EXA_API_KEY` | 可选 | 不设置 | 不设置 | 可选 | Exa 语义搜索（补充 Tavily） | 该搜索源被跳过 | **是** |

---

## 五、认证与安全

| 变量名 | 必需级别 | local-dev 默认 | local-docker 默认 | prod-like | 用途 | 缺失行为 | 敏感 |
|---|---|---|---|---|---|---|---|
| `JWT_SECRET` | **必需** | `REPLACE_ME_jwt_secret_min_32_chars` | 同左，compose 强制校验 | **必须显式设置，长度≥32** | JWT Token 签发/验证密钥 | 后端启动失败，所有认证不可用 | **是** |
| `API_AUTH_KEYS` | **必需** | `REPLACE_ME_api_key_1,REPLACE_ME_api_key_2` | 同左，compose 强制校验 | **必须显式设置** | 内部服务间 API Key（逗号分隔多个） | 后端启动失败 | **是** |
| `API_AUTH_ENABLED` | 可选 | `true` | `true` | `true`（**不可改为 false**） | 是否启用 API Key 鉴权门控 | false 时所有接口无鉴权暴露，**高危** | 否 |
| `RATE_LIMIT_ENABLED` | 可选 | `true` | `true` | `true`（**不可改为 false**） | 是否启用速率限制 | false 时无限速保护 | 否 |
| `CORS_ALLOW_ORIGINS` | 可选 | `http://localhost:5174` | `http://localhost:5174` | **必须设置为真实域名** | 允许的 CORS Origin（逗号分隔） | prod 若沿用 localhost 则跨域全部被浏览器拦截 | 否 |
| `VITE_SUPABASE_URL` | 可选 | 不设置 | 不设置 | 视是否启用 Supabase Auth | Supabase 项目 URL | Supabase Auth 不可用，降级本地 JWT | 否 |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | 可选 | 不设置 | 不设置 | 视需要 | Supabase Anon/Publishable Key | Supabase Auth 不可用 | **是** |

---

## 六、告警调度

| 变量名 | 必需级别 | local-dev 默认 | local-docker 默认 | prod-like | 用途 | 缺失行为 | 敏感 |
|---|---|---|---|---|---|---|---|
| `PRICE_ALERT_SCHEDULER_ENABLED` | 可选 | `false` | `true` | `true` | 启用价格告警定时任务 | 不设置时按环境默认（dev false） | 否 |
| `NEWS_ALERT_SCHEDULER_ENABLED` | 可选 | `false` | `true` | `true` | 启用新闻告警定时任务 | 不设置时按环境默认（dev false） | 否 |
| `RISK_ALERT_SCHEDULER_ENABLED` | 可选 | `false` | `true` | `true` | 启用风险告警定时任务 | 不设置时按环境默认（dev false） | 否 |

> local-dev 默认关闭调度器，避免频繁外部 API 调用消耗配额。正式部署或 docker 模式默认开启。

---

## 七、前端运行时

| 变量名 | 必需级别 | local-dev 默认 | local-docker 默认 | prod-like | 用途 | 缺失行为 | 敏感 |
|---|---|---|---|---|---|---|---|
| `VITE_API_BASE_URL` | 可选 | 空（自动推导） | 空（同源代理推导） | 推荐显式设置 | 前端请求的 API Base URL | 空时自动推导：dev(5173/5174)→`:8000`；nginx 容器→同 origin | 否 |

**自动推导逻辑（`frontend/src/lib/runtime.ts`）**：

```
if (VITE_API_BASE_URL 非空) → 使用该值
else if (当前 port 为 5173 或 5174) → http://localhost:8000
else → 同 origin（nginx 反向代理到 backend）
```

容器内 nginx 将 `/api/` 代理到 backend:8000，无需显式配置。

---

## 八、RAG / 嵌入模型

| 变量名 | 必需级别 | local-dev 默认 | local-docker 默认 | prod-like | 用途 | 缺失行为 | 敏感 |
|---|---|---|---|---|---|---|---|
| `RAG_V2_BACKEND` | 可选 | `auto` | compose 强制 `postgres` | `postgres` | RAG 向量存储后端 | auto 模式自动检测 PG 连通性 | 否 |
| `RAG_EMBEDDING` | 可选 | 不设置（默认加载 BGE-M3） | 不设置 | 不设置 | 嵌入模型选择；smoke 环境设为 `hash` 跳过模型加载 | 默认加载 BGE-M3，首次启动较慢 | 否 |

> smoke 环境（`docker-compose.smoke.yml`）强制设置 `RAG_EMBEDDING=hash`，跳过 BGE-M3 下载，加速 CI 冷启动。

---

## 九、可观测性（LangSmith / Langfuse）

| 变量名 | 必需级别 | local-dev 默认 | local-docker 默认 | prod-like | 用途 | 缺失行为 | 敏感 |
|---|---|---|---|---|---|---|---|
| `LANGSMITH_API_KEY` | 可选 | 不设置 | 不设置 | 可选 | LangSmith Tracing Key | Tracing 静默禁用 | **是** |
| `ENABLE_LANGSMITH` | 可选 | `false` | `false` | `false`（按需开启） | 是否开启 LangSmith Tracing | 默认关闭 | 否 |
| `LANGFUSE_ENABLED` | 可选 | `false` | `false` | `false`（按需开启） | 是否开启 Langfuse 可观测性 | 默认关闭 | 否 |
| `LANGFUSE_PUBLIC_KEY` | 可选 | 不设置 | 不设置 | 视需要 | Langfuse Public Key | Langfuse 不可用 | **是** |
| `LANGFUSE_SECRET_KEY` | 可选 | 不设置 | 不设置 | 视需要 | Langfuse Secret Key | Langfuse 不可用 | **是** |
| `LANGFUSE_HOST` | 可选 | 不设置 | 不设置 | 视需要 | Langfuse 自托管地址（默认 cloud） | 使用 Langfuse Cloud | 否 |
| `LOG_LEVEL` | 可选 | `INFO` | `INFO` | `INFO`（prod 可调为 `WARNING`） | 日志级别 | 默认 INFO | 否 |

---

## 十、邮件 SMTP（告警通知）

| 变量名 | 必需级别 | local-dev 默认 | local-docker 默认 | prod-like | 用途 | 缺失行为 | 敏感 |
|---|---|---|---|---|---|---|---|
| `SMTP_SERVER` | 可选 | 不设置 | 不设置 | 推荐设置 | SMTP 服务器地址 | 邮件告警静默禁用 | 否 |
| `SMTP_PORT` | 可选 | `587` | `587` | `587`（或 `465` TLS） | SMTP 端口 | 默认 587 | 否 |
| `SMTP_USER` | 可选 | 不设置 | 不设置 | 推荐设置 | SMTP 登录用户名 | 邮件发送失败 | **是** |
| `SMTP_PASSWORD` | 可选 | 不设置 | 不设置 | 推荐设置 | SMTP 登录密码/授权码 | 邮件发送失败 | **是** |
| `EMAIL_FROM` | 可选 | 不设置 | 不设置 | 推荐设置 | 发件人地址 | 邮件发送失败 | 否 |

---

## 快速参考：各环境最小必需集

### local-dev（裸跑）

```bash
# .env（最小集）
OPENAI_COMPATIBLE_API_KEY=REPLACE_ME_llm_api_key
OPENAI_COMPATIBLE_API_BASE=https://api.openai.com/v1
OPENAI_COMPATIBLE_MODEL=gpt-4o-mini
POSTGRES_DB=finsight
POSTGRES_USER=finsight
POSTGRES_PASSWORD=REPLACE_ME_db_password
JWT_SECRET=REPLACE_ME_jwt_secret_min_32_chars_here
API_AUTH_KEYS=REPLACE_ME_api_key_1
DEV_MODE=1
```

### local-docker（dev compose）

在上述基础上，`docker-compose.dev.yml` 额外注入：
- `DEV_MODE=1`
- postgres 暴露 `5432` 到宿主机
- backend 暴露 `8000` 到宿主机
- frontend 暴露 `5174:80`

### prod-like（prod compose）

在最小必需集基础上，**额外要求**：
- **删除** `DEV_MODE`（或确保不设置）
- `CORS_ALLOW_ORIGINS` 设为真实域名
- `API_AUTH_ENABLED=true`、`RATE_LIMIT_ENABLED=true`（可显式确认）
- 所有调度器按需开启（`*_SCHEDULER_ENABLED=true`）
- 推荐配置至少一个行情 API Key 和 `TAVILY_API_KEY`

---

## 安全检查清单

- [ ] `.env` 已加入 `.gitignore`，不会提交到版本库
- [ ] `JWT_SECRET` 长度 ≥ 32 字符，使用随机字符串
- [ ] prod 环境 **未设置** `DEV_MODE` 或其值不为 `1`
- [ ] `CORS_ALLOW_ORIGINS` 未包含 `*` 通配符
- [ ] `API_AUTH_ENABLED` 和 `RATE_LIMIT_ENABLED` 均为 `true`
- [ ] smoke 环境使用独立 volume / 容器名，不影响 dev 数据
- [ ] 所有 `*_API_KEY` 类变量未以明文出现在日志中（`LOG_LEVEL` ≠ `DEBUG` on prod）
