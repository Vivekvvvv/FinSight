# PHASE8_EXTERNAL_API_SMOKE_REPORT.md

**生成时间**：2026-06-09  
**阶段**：Phase 8 — 外部 API / LLM Smoke 验证  
**结论**：PARTIAL（LLM key 无效，行情 key 未配置；均为环境问题，非代码问题）

---

## 1. LLM API Smoke

| 项目 | 值 |
|------|---|
| 端点 | `https://grok.jiuuij.de5.net/v1/chat/completions` |
| 模型 | `grok-4.1-fast` |
| API Key | `<invalid-test-key-redacted>`（`.env.server` 中配置的无效测试值，已脱敏） |
| 结果 | ❌ HTTP 403 — `{"detail":"Invalid API key."}` |
| 延迟 | 1637ms（网络连通，key 本身无效） |

**分析**：网络层可达（1.6s 内收到 403 响应），脱敏测试 key 为无效凭据。代码路径无问题，需在部署时替换为有效 key。

**代码层验证**（已在 Phase 7 通过）：
- `/api/chat` 端点路由正常（HTTP 200）
- `OPENAI_COMPATIBLE_*` 环境变量读取链路正常
- 错误 fallback（LLM 不可用时返回结构化错误，不崩溃）

---

## 2. 行情数据 API Smoke

| API | Key 状态 | 结果 |
|-----|---------|------|
| Alpha Vantage | 占位符 `your_key_here` | ⚠️ NOT_TESTED（key 缺失） |
| Finnhub | 占位符 `your_key_here` | ⚠️ NOT_TESTED（key 缺失） |
| Polygon | 占位符 `your_key_here` | ⚠️ NOT_TESTED（key 缺失） |

**注**：Phase 8 Docker smoke 中 `PUT /api/portfolio/positions/AAPL` 返回 `live_price=301.54`（`price_source=tools_bridge`），证明 `tools_bridge` 在 DEV_MODE 下正常返回模拟价格，系统不崩溃。

---

## 3. RAG / 向量搜索

| 项目 | 状态 | 说明 |
|------|------|------|
| smoke 模式（`RAG_EMBEDDING=hash`） | ✅ PASS | Docker smoke 全程无向量相关报错 |
| BGE-M3 模型下载 | ⚠️ NOT_VERIFIED_ENV_LIMIT | 需要下载约 1.4GB，当前网络环境受限；生产部署前需单独验证 |

---

## 4. 总结

| 类别 | 状态 | 阻塞生产？ |
|------|------|---------|
| LLM API（代码路径） | ✅ PASS | — |
| LLM API（key 有效性） | ❌ FAIL | ✅ 阻塞（需有效 key） |
| 行情 API（代码路径） | ✅ PASS（DEV_MODE 模拟） | — |
| 行情 API（key 有效性） | ⚠️ NOT_TESTED | 功能降级，不崩溃 |
| RAG hash fallback | ✅ PASS | — |
| BGE-M3 生产 embedding | ⚠️ NOT_VERIFIED | 生产前需验证 |

---

## 5. 行动项

| 优先级 | 行动 |
|--------|------|
| P0 | 替换 `OPENAI_COMPATIBLE_API_KEY` 为有效 key，重新验证 LLM |
| P1 | 配置至少 1 个行情 key（AlphaVantage 免费版） |
| P1 | 在网络可用环境下执行 `python -m backend.rag.download_models` 下载 BGE-M3 |
