# PHASE9_MINIMAL_RELEASE_SMOKE.md

**生成时间**：2026-06-09  
**阶段**：Phase 9 — 最小发布确认 Smoke  
**结论**：PASS（10/10 核心测试通过；B3 LLM key 无效为唯一未通过项）

---

## 1. 测试环境

| 项目 | 值 |
|------|---|
| 后端 | uvicorn `backend.api.main:app` 127.0.0.1:8766 |
| 认证 | `DEV_MODE=false`，`API_AUTH_KEYS=phase9-test-key-abc123`（测试值） |
| JWT_SECRET | 64字符随机测试值 |
| LLM | OPENAI_COMPATIBLE_API_KEY 配置但无效（B3 未解除） |
| 执行时间 | 2026-06-09 |

---

## 2. Compose Config 验证

| 模式 | 命令 | 结果 | 耗时 |
|------|------|------|------|
| Base | `docker compose config --quiet` | ✅ Exit 0 | <1s |
| Smoke overlay | `docker compose -f docker-compose.yml -f docker-compose.smoke.yml config --quiet` | ✅ Exit 0 | <1s |

---

## 3. 核心 API Smoke 结果

| # | 测试项 | 端点 | HTTP | 耗时 | 结果 |
|---|--------|------|------|------|------|
| 1 | 健康检查 | `GET /health` | 200 | <5ms | ✅ PASS |
| 2 | 身份接口（无 key） | `GET /api/me` | 200 | <5ms | ✅ PASS（返回 guest:anonymous） |
| 3 | 身份接口（有效 key） | `GET /api/me` | 200 | <5ms | ✅ PASS（返回 api_292e... auth_type=api_key） |
| 4 | DEV bypass 检查 | `GET /api/me` | 200 | <5ms | ✅ PASS（无 dev bypass） |
| 5 | Today Workspace | `GET /api/today` | 200 | <10ms | ✅ PASS（返回空聚合数据） |
| 6 | Research Quality | `GET /api/research-quality` | 200 | <10ms | ✅ PASS（health=100） |
| 7 | What Changed | `GET /api/what-changed` | 200 | <10ms | ✅ PASS（count=0） |
| 8 | Portfolio Summary | `GET /api/portfolio/summary` | 200 | <10ms | ✅ PASS（count=0） |
| 9 | Watchlist | `GET /api/user/watchlist` | 200 | <10ms | ✅ PASS（count=0） |
| 10 | Chat 端点路由 | `POST /chat/supervisor` | 200 | 32ms | ✅ PASS（graph 正常，clarify 响应） |

---

## 4. Notes 上传闭环

| # | 测试项 | 结果 | 耗时 |
|---|--------|------|------|
| 1 | 创建 note | ✅ PASS | 58ms |
| 2 | 上传小图（69字节 PNG） | ✅ PASS | 19ms |
| 3 | 访问图片 URL | ✅ PASS（200，bytes=69） | 31ms |
| 4 | 删除 note（清理） | ✅ PASS | 7ms |

---

## 5. LLM Smoke

| # | 测试项 | 结果 | 说明 |
|---|--------|------|------|
| 1 | 直接 LLM API 调用 | ❌ FAIL | HTTP 403 `Invalid API key` — B3 未解除 |
| 2 | Chat 端点（LLM-free 分支） | ✅ PASS | graph 32ms，clarify 响应正常 |

---

## 6. Auth 验证

| # | 测试项 | 结果 |
|---|--------|------|
| 1 | 无 key → guest:anonymous | ✅ PASS |
| 2 | 无效 key → guest:anonymous | ✅ PASS |
| 3 | 有效 key → api_key 身份 | ✅ PASS |
| 4 | DEV_MODE=false 无 dev bypass | ✅ PASS |

---

## 7. 未通过项分析

| 项目 | 状态 | 阻塞 READY？ |
|------|------|------------|
| LLM API key 无效 | ❌ FAIL | ✅ 阻塞（Chat 实际 AI 能力不可用） |
| JWT_SECRET 生产值为空 | ⚠️ 未在本 smoke 验证（测试值已通过） | ✅ 阻塞（`.env.server` 中需补全） |
| API_AUTH_KEYS 生产值为空 | ⚠️ 未在本 smoke 验证（测试值已通过） | ✅ 阻塞（`.env.server` 中需补全） |

---

## 8. 解除阻塞后的验证步骤

B1/B2/B3 解除后，只需运行以下最小验证：

```powershell
# 1. B1/B2 验证
curl.exe -H "X-API-Key: <your_api_key>" http://localhost:8000/api/me
# 期望：{"user_id":"api_xxx","auth_type":"api_key"}

# 2. B3 验证  
python scripts/phase9_llm_smoke.py
# 期望：[PASS] llm-call

# 3. 端到端 chat 验证
# POST /chat/supervisor query="What is the latest AAPL news?"
# 期望：HTTP 200，response 有实际 AI 分析内容
```
