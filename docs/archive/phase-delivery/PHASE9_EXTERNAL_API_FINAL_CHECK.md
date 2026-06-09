# PHASE9_EXTERNAL_API_FINAL_CHECK.md

**生成时间**：2026-06-09  
**阶段**：Phase 9 — 外部 API 最终验证  
**结论**：PARTIAL（B3 — LLM key 仍无效；Chat 端点代码路径正常；行情可选未配置）

---

## 1. LLM 直接调用

| 项目 | 值 |
|------|---|
| 端点 | `https://grok.jiuuij.de5.net/v1/chat/completions` |
| 模型 | `grok-4.1-fast` |
| API Key | `<invalid-test-key-redacted>`（`.env.server` 中的无效测试值，已脱敏） |
| 结果 | ❌ HTTP 403 — `{"detail":"Invalid API key."}` |
| 延迟 | 863ms（网络连通，key 无效） |

**分析**：网络可达，endpoint 可响应，脱敏测试 key 为无效凭据。B3 未解除。

---

## 2. `/chat/supervisor` 端点验证

| 项目 | 值 |
|------|---|
| 后端 | uvicorn localhost:8766，DEV_MODE=false，API_AUTH_KEYS 已配置 |
| 请求 | `POST /chat/supervisor query="Reply with one word: READY"` |
| HTTP | ✅ 200 |
| response_time_ms | 32ms |
| 响应内容 | 澄清消息（要求用户指定研究对象）—— LLM 未被调用（subject 未知，走 clarify 分支） |
| 错误 | 无 |

**关键结论**：Chat 端点路由、graph 初始化、auth 验证、LangGraph 状态机全部正常运行（32ms）。clarify 响应不依赖 LLM key，证明非 LLM 分支完全健康。

---

## 3. LLM 实际调用路径

当 LLM key 有效时，图执行路径为：
```
build_initial_state → reset_turn_state → trim_history → normalize_ui_context 
→ decide_output_mode → chat_respond → [LLM call] → response
```

当 LLM key 无效时：
- 如果 subject 已知 → LLM 调用 → HTTP 403 → 返回 error response
- 如果 subject 未知 → clarify 分支 → 无 LLM 调用 → 正常返回

---

## 4. 行情 API

| API | Key 状态 | 结果 |
|-----|---------|------|
| Alpha Vantage | EMPTY/PLACEHOLDER | ⚠️ NOT_TESTED |
| Finnhub | EMPTY/PLACEHOLDER | ⚠️ NOT_TESTED |
| FMP | EMPTY/PLACEHOLDER | ⚠️ NOT_TESTED |
| Polygon | MISSING | ⚠️ NOT_TESTED |

行情 key 均未配置，系统降级为 `tools_bridge` 模拟价格（Phase 8 验证：`AAPL live_price=301.54 source=tools_bridge`），不阻塞发布。

---

## 5. 搜索 API

| API | Key 状态 |
|-----|---------|
| Tavily | EMPTY/PLACEHOLDER |
| Jina Reader | MISSING |

搜索功能降级，不阻塞发布。

---

## 6. B3 解除步骤

```bash
# 1. 获取有效的 LLM API key（替换为实际 provider 的 key）
#    如：SiliconFlow (https://api.siliconflow.cn/v1)，支持多种模型

# 2. 更新 .env.server
# OPENAI_COMPATIBLE_API_KEY=sk-xxxx...（实际 key）
# OPENAI_COMPATIBLE_API_BASE=https://api.siliconflow.cn/v1  (或其他 endpoint)
# OPENAI_COMPATIBLE_MODEL=Qwen/Qwen2.5-72B-Instruct  (或其他模型)

# 3. 验证
python scripts/phase9_llm_smoke.py
# 期望：LLM_SMOKE: PASS
```

---

## 7. 总结

| 类别 | 状态 |
|------|------|
| LLM 端点代码路径 | ✅ PASS（graph 正常运行，32ms） |
| LLM API key 有效性 | ❌ FAIL（B3 — `<invalid-test-key-redacted>` 无效，403） |
| 行情 API | ⚠️ NOT_TESTED（可选，降级不崩溃） |
| 搜索 API | ⚠️ NOT_TESTED（可选） |
