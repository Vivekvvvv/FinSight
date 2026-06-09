# Phase 7 API Smoke 报告

**日期**: 2026-06-08  
**状态**: ✅ **12/12 通过 | Bug 已修复**

---

## 执行摘要

- **后端**: `DEV_MODE=1 uvicorn backend.api.main:app --port 8001`
- **Session**: `public:anonymous:phase7-smoke`
- **测试接口**: 12 个关键接口
- **结果**: 12/12 通过

---

## 接口测试结果

### [1] Health & Auth

| 接口 | 状态码 | 响应时间 | 结果 |
|------|--------|---------|------|
| GET /health | 200 | 43ms | ✅ `{"status":"ok","version":"1.0.0"}` |
| GET /api/me | 200 | 1ms | ✅ `{"success":true,"user_id":"default_user","auth_type":"dev"}` |

### [2] Today Workspace

| 接口 | 状态码 | 响应时间 | 结果 |
|------|--------|---------|------|
| GET /api/today | 200 | 5ms | ✅ `{success, portfolio_snapshot, next_actions, ...}` |

### [3] Research APIs

| 接口 | 状态码 | 响应时间 | 结果 |
|------|--------|---------|------|
| GET /api/research-quality | 200 | 2ms | ✅ `{success, summary{health_score,...}, top_issues}` |
| GET /api/what-changed | 200 | 2ms | ✅ `{success, items:[], count:0}` |
| GET /api/research-notes | 200 | 2ms | ✅ `{success, notes:[]}` |

> 注：research-quality 和 what-changed 在修复 `require_matching_identity` 后恢复 200。

### [4] Portfolio & Watchlist

| 接口 | 状态码 | 响应时间 | 结果 |
|------|--------|---------|------|
| GET /api/portfolio/summary | 200 | 7ms | ✅ `{success, positions:[], count:0}` |
| GET /api/portfolio/risk-lens | 200 | 2ms | ✅ `{success, risk_score, ...}` |
| GET /api/user/watchlist | 200 | 1ms | ✅ `{success, items:[], count:0}` |

### [5] Reports & Timeline

| 接口 | 状态码 | 响应时间 | 结果 |
|------|--------|---------|------|
| GET /api/reports/index | 200 | 3ms | ✅ `{success, items:[], count:0}` |
| GET /api/timeline/AAPL | 200 | 3ms | ✅ `{success, events:[], symbol:"AAPL"}` |

### [6] Alerts

| 接口 | 状态码 | 响应时间 | 结果 |
|------|--------|---------|------|
| GET /api/alerts/feed | 200 | 1ms | ✅ `{success, events:[]}` |

---

## 修复的 Bug

### `require_matching_identity` 调用方式不兼容 (P1)

**症状**: `/api/research-quality` + `/api/what-changed` 返回 HTTP 500

**根因**: 
```python
# auth.py 中函数签名为 keyword-only
def require_matching_identity(*, principal, provided, expected, field_name): ...

# 两个路由错误地用位置参数
require_matching_identity(current_user, user_id, session_id)  # TypeError
```

**修复**:
- `backend/api/research_quality_router.py:29`
- `backend/api/what_changed_router.py:32`

---

## 文件系统 / 上传验证

| 测试 | 结果 |
|------|------|
| POST /api/research-notes（创建笔记） | ✅ 200 |
| POST /api/research-notes/{id}/images（上传 PNG） | ✅ 200，返回访问 URL |
| GET /api/notes/images/{user}/{note}/{file} | ✅ 200，image/png，72B |
| 路径遍历 `../../etc/passwd` | ✅ 404 拦截 |
| URL 编码路径遍历 `%2e%2e` | ✅ 404 拦截 |

---

## 空态行为验证

全部接口在空数据库下返回合理空态（`items:[]`, `count:0`, `success:true`），不返回 500 或 null。

---

## 注意事项

1. **行情 API (`/api/quote/AAPL`)**: 需要真实 API key 才能返回数据，无 key 时请求外部服务超时（>10s），属预期行为
2. **DEV_MODE user_id**: dev 模式下 `principal.user_id` 固定为 `default_user`，与请求参数中的 `user_id` 不同；创建资源时要用 `default_user` 才能通过权限检查
3. **LLM 功能**: `/chat` 端点无 LLM key 时会返回错误提示，属预期行为
