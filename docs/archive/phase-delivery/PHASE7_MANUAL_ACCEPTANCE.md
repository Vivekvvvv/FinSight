# Phase 7 手动验收清单

**日期**: 2026-06-08  
**状态**: ✅ **API 层全通过 | 前端浏览器验收需真实环境**

---

## 说明

Phase 7 手动验收分两部分：
1. **API 层验收**（已完成）：通过 curl + Python 脚本验证后端接口，全部通过
2. **浏览器 UI 验收**（受环境限制）：需要前端 dev server 或 Docker nginx 服务

---

## API 层验收（已执行）

### 核心页面对应接口

| 页面 | 接口 | 状态 |
|------|------|------|
| /welcome | GET /api/today | ✅ 200，返回完整结构 |
| /welcome | GET /api/what-changed | ✅ 200 (修复后) |
| /welcome | GET /api/research-quality | ✅ 200 (修复后) |
| /dashboard/AAPL | GET /api/quote/AAPL | ⚠️ 超时（无行情 key，预期行为） |
| /reports | GET /api/reports/index | ✅ 200 |
| /portfolio | GET /api/portfolio/summary | ✅ 200 |
| /portfolio/risk-lens | GET /api/portfolio/risk-lens | ✅ 200 |
| /notes | GET /api/research-notes | ✅ 200 |
| /timeline/AAPL | GET /api/timeline/AAPL | ✅ 200 |
| /watchlist | GET /api/user/watchlist | ✅ 200 |
| /alerts | GET /api/alerts/feed | ✅ 200 |

### 交互操作验收

| 操作 | 状态 |
|------|------|
| 创建 watchlist 条目 | ✅ POST /api/user/watchlist/add → 200 |
| 创建 portfolio position | ✅ POST /api/portfolio/positions → 200 |
| 创建 research note | ✅ POST /api/research-notes → 200 |
| 上传图片到 note | ✅ POST /api/research-notes/{id}/images → 200，PNG 72B 读取成功 |
| 路径遍历防护 | ✅ 404 拦截 `../../etc/passwd` |
| 打开 timeline | ✅ /api/timeline/AAPL → 200 |
| 打开 risk lens | ✅ /api/portfolio/risk-lens → 200 |
| 打开 reports library | ✅ /api/reports/index → 200 |
| Chat 无 LLM key | ✅ 返回错误提示（非 500 崩溃） |

---

## 空态行为

| 接口 | 空态响应 | 评价 |
|------|---------|------|
| /api/reports/index | `{success:true, items:[], count:0}` | ✅ 合理 |
| /api/portfolio/summary | `{success:true, positions:[], count:0}` | ✅ 合理 |
| /api/user/watchlist | `{success:true, items:[], count:0}` | ✅ 合理 |
| /api/research-notes | `{success:true, notes:[]}` | ✅ 合理 |
| /api/what-changed | `{success:true, items:[], count:0}` | ✅ 合理 |
| /api/today | `{success:true, portfolio_snapshot:{position_count:0,...}, next_actions:[...]}` | ✅ 合理，空态有引导 action |

---

## 浏览器 UI 验收（待执行）

前端 E2E 测试（48/48 全绿）已覆盖主要 UI 交互。真实浏览器验收需要：

```bash
# 启动 dev server
cd frontend-vue
npm run dev  # 访问 http://localhost:5174

# 同时启动后端
DEV_MODE=1 uvicorn backend.api.main:app --port 8000
```

**待验收项目**（Playwright E2E 已覆盖）：
- [ ] /welcome — 页面打开，今日工作台显示
- [ ] /chat — 快捷问题显示，输入框可用
- [ ] /dashboard/AAPL — 搜索框可用（报价卡需 API key）
- [ ] /reports — 报告库列表（空态合理）
- [ ] /portfolio — 持仓列表（空态 + 添加按钮）
- [ ] /portfolio/risk-lens — 风险透镜（空态合理）
- [ ] /notes — 笔记列表，可创建，可上传图片
- [ ] /timeline/AAPL — 时间线（空态合理）
- [ ] /watchlist — 自选清单（空态 + 添加按钮）
- [ ] /alerts — 告警中心

---

## 已知非阻塞问题

1. **行情数据**: 无真实行情 API key 时 `/api/quote/*` 超时，前端应显示加载中/错误态（已通过 Playwright mock 测试验证）
2. **LLM 功能**: 无 LLM key 时 Chat 返回错误提示，非崩溃
3. **移动端**: Playwright 测试不含移动端视口测试，待手动验收
4. **DEV_MODE user_id**: 实际部署需关闭 DEV_MODE，API key 认证生效后 user_id 正确传播
