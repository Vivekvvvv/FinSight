# PHASE8_STAGING_ENV_REPORT.md

**生成时间**：2026-06-09  
**阶段**：Phase 8 — 生产 Staging 环境变量审计  
**结论**：NOT_READY（2 项 BLOCKING，需在上线前补全）

---

## 1. 审计范围

文件：`.env.server`（生产部署模板）  
方法：逐项核查必填字段是否有实际值、是否为占位符、是否为安全值

---

## 2. 安全凭据（Security）

| 变量 | 状态 | 说明 |
|------|------|------|
| `JWT_SECRET` | ❌ **BLOCKING — MISSING** | `.env.server` 中值为空字符串；任何人都可以伪造 JWT token |
| `API_AUTH_KEYS` | ❌ **BLOCKING — MISSING** | `.env.server` 中值为空字符串；API 无访问控制 |
| `DEV_MODE` | ✅ 未设置（正确） | 生产环境不应设置 DEV_MODE=1 |

---

## 3. LLM / AI 配置（Intelligence）

| 变量 | 状态 | 说明 |
|------|------|------|
| `OPENAI_COMPATIBLE_API_KEY` | ⚠️ SET（len=13） | 已配置，但值较短；需确认是有效 key |
| `OPENAI_COMPATIBLE_BASE_URL` | 未验证 | 需确认与 key 匹配的 endpoint |
| `OPENAI_COMPATIBLE_MODEL` | 未验证 | 需确认部署支持的模型名 |

---

## 4. 行情数据 API（Market Data）

| 变量 | 状态 | 说明 |
|------|------|------|
| `ALPHA_VANTAGE_API_KEY` | ⚠️ 占位符 `your_key_here` | 未配置；行情功能降级为模拟数据 |
| `FINNHUB_API_KEY` | ⚠️ 占位符 `your_key_here` | 未配置 |
| `POLYGON_API_KEY` | ⚠️ 占位符 `your_key_here` | 未配置 |

行情 key 未配置时，`tools_bridge` 返回模拟价格，不影响系统启动，但生产环境功能受限。

---

## 5. 数据库配置（Database）

| 变量 | 状态 | 说明 |
|------|------|------|
| `DATABASE_URL` | 未验证 | 需确认指向生产 DB，不连接本地 smoke DB |
| `POSTGRES_PASSWORD` | 未验证 | 需确认非默认密码 |

---

## 6. RAG / 向量搜索（RAG）

| 变量 | 状态 | 说明 |
|------|------|------|
| `RAG_EMBEDDING` | 未设置（正确） | 生产环境应使用 BGE-M3，不应设置为 `hash` |
| `RAG_V2_ALLOW_MEMORY_FALLBACK` | 未设置 | 若首次部署向量库为空，考虑临时启用 |

---

## 7. 行动项（上线前必须完成）

| 优先级 | 行动 | 负责人 |
|--------|------|--------|
| P0 | 生成强随机 `JWT_SECRET`（≥64字符），写入 `.env.server` | 部署者 |
| P0 | 生成 `API_AUTH_KEYS`（至少 1 个 token），写入 `.env.server` | 部署者 |
| P1 | 验证 `OPENAI_COMPATIBLE_API_KEY` 可调通 LLM | 部署者 |
| P1 | 配置 `DATABASE_URL` 指向生产数据库 | 部署者 |
| P2 | 配置至少 1 个行情 key（Alpha Vantage 免费版即可） | 可选 |
| P2 | 下载 BGE-M3 模型（或配置 `RAG_EMBEDDING=hash` 临时跳过） | 部署者 |

---

## 8. Smoke Env 对照

Phase 8 Docker smoke 使用随机 GUID 生成的 JWT_SECRET 和 API_AUTH_KEYS，与生产无关。Smoke 环境已验证系统在有效凭据下正常运行。生产部署只需按上述行动项补全真实 key。
