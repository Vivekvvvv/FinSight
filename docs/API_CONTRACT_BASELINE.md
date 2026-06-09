# API 契约基线

当前默认契约为:

```text
frontend-vue/src/api/client.ts -> backend/FastAPI
```

## 核心原则

- FastAPI 是唯一默认后端入口。
- Vue 前端直接消费 FastAPI 响应, 不依赖中间网关包装。
- 新增字段必须保持向后兼容, 不删除前端正在使用的字段。
- SSE、RAG、LLM、Dashboard、报告和订阅能力都以 Python 实现为准。

## Vue 当前使用的端点

| 功能 | 端点 |
|---|---|
| 身份 | `GET /api/me` |
| 权益 | `GET /api/me/entitlements`, `GET /api/me/usage`, `GET /api/plans` |
| 对话 | `POST /chat/supervisor/stream` |
| Dashboard | `GET /api/dashboard`, `GET /api/dashboard/insights` |
| Daily tasks | `GET /api/tasks/daily` |
| RAG Inspector | `GET /diagnostics/rag/status`, `GET /diagnostics/rag/runs` |
| Watchlist | `GET /api/user/watchlist`, `POST /api/user/watchlist/add`, `POST /api/user/watchlist/update`, `POST /api/user/watchlist/remove` |
| Portfolio | `GET /api/portfolio/summary`, `PUT /api/portfolio/positions/{ticker}`, `DELETE /api/portfolio/positions/{ticker}` |
| Reports | `GET /api/reports/index`, `POST /api/reports/{report_id}/favorite` |
| Alerts | `GET /api/subscriptions`, `POST /api/subscription/toggle`, `POST /api/unsubscribe`, `GET /api/alerts/feed` |

## 变更流程

1. 先修改 FastAPI 路由或服务。
2. 同步更新 `frontend-vue/src/api/types.ts`。
3. 同步更新 `frontend-vue/src/api/client.ts`。
4. 补后端测试或前端类型/构建验证。
5. 运行 `python scripts/check_cutover_map.py` 确认默认链路没有回到旧网关。
