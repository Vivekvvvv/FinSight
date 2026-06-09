# PHASE9_SECRET_READINESS_REPORT.md

**生成时间**：2026-06-09  
**阶段**：Phase 9 — 密钥就绪性检查  
**方法**：脚本扫描 `.env.server`，不打印真实值，只记录 PRESENT / MISSING / EMPTY/PLACEHOLDER  
**结论**：NOT_READY（B1/B2 阻塞；B3 key 配置但待验证有效性）

---

## 1. P0 安全凭据

| 变量 | 状态 | 阻塞生产？ |
|------|------|---------|
| `JWT_SECRET` | ❌ MISSING | ✅ 阻塞（B1） |
| `API_AUTH_KEYS` | ❌ MISSING | ✅ 阻塞（B2） |
| `DEV_MODE` | ✅ 未设置（默认 false） | — |

---

## 2. LLM Provider

| 变量 | 状态 | 说明 |
|------|------|------|
| `OPENAI_COMPATIBLE_API_KEY` | ✅ PRESENT | `<invalid-test-key-redacted>` — Phase 8 验证 HTTP 403（无效） |
| `OPENAI_COMPATIBLE_API_BASE` | ✅ PRESENT (len=47) | `https://grok.jiuuij.de5.net/v1/chat/completions` |
| `OPENAI_COMPATIBLE_MODEL` | ✅ PRESENT (len=13) | `grok-4.1-fast` |
| `LLM_API_BASE` | ✅ PRESENT (len=29) | `https://api.siliconflow.cn/v1` |
| `OPENAI_API_KEY` | ❌ MISSING | — |
| `GEMINI_PROXY_API_KEY` | ❌ MISSING | — |
| `DEEPSEEK_API_KEY` | ❌ MISSING | — |

**B3 状态**：key 配置存在但 Phase 8 验证为 HTTP 403（无效），Phase 9 将重新验证。

---

## 3. 行情数据（可选）

| 变量 | 状态 | 说明 |
|------|------|------|
| `FMP_API_KEY` | ⚠️ EMPTY/PLACEHOLDER | 未配置，行情降级为模拟数据 |
| `FINNHUB_API_KEY` | ⚠️ EMPTY/PLACEHOLDER | 未配置 |
| `ALPHA_VANTAGE_API_KEY` | ⚠️ EMPTY/PLACEHOLDER | 未配置 |
| `POLYGON_API_KEY` | ❌ MISSING | 未配置 |

行情 key 均未配置，系统降级为 tools_bridge 模拟价格，不阻塞发布。

---

## 4. 搜索（可选）

| 变量 | 状态 |
|------|------|
| `TAVILY_API_KEY` | ⚠️ EMPTY/PLACEHOLDER |
| `JINA_READER_BASE_URL` | ❌ MISSING |

---

## 5. 数据库

| 变量 | 状态 |
|------|------|
| `POSTGRES_USER` | ✅ PRESENT (len=8) |
| `POSTGRES_PASSWORD` | ✅ PRESENT (len=25) |
| `POSTGRES_DB` | ✅ PRESENT (len=8) |
| `DATABASE_URL` | ❌ MISSING（用分散变量代替，可接受） |

---

## 6. 应用配置

| 变量 | 状态 | 说明 |
|------|------|------|
| `CORS_ORIGINS` | ❌ MISSING | 将使用代码默认值（localhost 列表，不含 `*`）— 生产需改为实际域名 |
| `RAG_EMBEDDING` | ✅ PRESENT — `bge-m3` | 生产模式，需确认模型已下载 |
| `VITE_API_BASE_URL` | ✅ PRESENT (len=21) | `http://localhost:8000`（Docker nginx 代理环境下前端用相对路径，此值仅本地开发用） |

---

## 7. SMTP（可选）

| 变量 | 状态 |
|------|------|
| `SMTP_USER` | ✅ PRESENT (len=20) |
| `SMTP_PASSWORD` | ✅ PRESENT (len=22) |
| `SMTP_HOST` | ❌ MISSING |

SMTP 可选，不阻塞发布。

---

## 8. 密钥安全性说明

- 本报告不包含任何密钥明文
- 所有检查通过脚本 `scripts/phase9_secret_check.py` 自动执行
- `.env.server` 已在 `.gitignore` 中，不会提交到仓库

---

## 9. 行动项

| 优先级 | 变量 | 操作 |
|--------|------|------|
| P0 | `JWT_SECRET` | 生成 ≥64 字符随机字符串并写入 `.env.server` |
| P0 | `API_AUTH_KEYS` | 生成至少 1 个 token 并写入 `.env.server` |
| P0 | `OPENAI_COMPATIBLE_API_KEY` | 替换为有效 key 并重新验证 |
| P1 | `CORS_ORIGINS` | 设置为实际前端域名（如 `https://app.example.com`） |
| P1 | `SMTP_HOST` | 配置 SMTP 服务器（如需邮件通知功能） |
| P2 | 行情 key | 按需配置（不阻塞发布） |
