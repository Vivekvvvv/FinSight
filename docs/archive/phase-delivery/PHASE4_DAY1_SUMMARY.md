# Phase 4.1 - Day 1: Portfolio Risk Lens 实施总结

## 完成时间
2026-06-08

## 实施范围
Portfolio Risk Lens 基础版本（规则引擎 + 后端 API + 前端组件）

---

## ✅ 后端实施

### 1. 核心规则引擎
**文件**: `backend/services/portfolio_risk_lens.py`

**功能**:
- 8 条风险检测规则
- 风险评分计算（0-100）
- 操作建议生成

**风险规则**:
1. **单一持仓集中度**: >25% 触发 high severity
2. **行业集中度**: >40% 触发 high severity
3. **币种暴露**: 统计各币种占比
4. **市场暴露**: US/HK/CN 市场识别
5. **亏损持仓**: -5% medium, -10% high
6. **过期研究**: 7 天 warning, 30 天 critical
7. **低质量覆盖**: >30% 报告质量问题
8. **高仓位无研究**: >10% 仓位但无报告覆盖

**关键参数** (RISK_RULES):
```python
{
    "single_position_high": 0.25,
    "single_sector_high": 0.40,
    "loss_medium_threshold": -0.05,
    "loss_high_threshold": -0.10,
    "stale_days_warning": 7,
    "stale_days_critical": 30,
    "low_quality_rate_threshold": 0.30,
    "high_position_no_research": 0.10,
}
```

### 2. API 路由
**文件**: `backend/api/risk_lens_router.py`

**端点**: `GET /api/portfolio/risk-lens?session_id=xxx&user_id=xxx`

**依赖注入模式**:
```python
@dataclass(frozen=True)
class RiskLensRouterDeps:
    resolve_thread_id: Callable[[Optional[str]], str]
```

**响应结构**:
```json
{
  "success": true,
  "as_of": "2026-06-08T...",
  "total_value": 10000,
  "total_cost": 9500,
  "risk_score": 45,
  "concentration_risk": [...],
  "sector_exposure": [...],
  "currency_exposure": [...],
  "market_exposure": [...],
  "stale_research": [...],
  "loss_positions": [...],
  "missing_coverage": [...],
  "next_actions": [...]
}
```

### 3. 主应用注册
**文件**: `backend/api/main.py`

- 已导入 `risk_lens_router`
- 已创建路由实例（依赖注入）
- 已注册到 FastAPI app: `app.include_router(risk_lens_router)`

---

## ✅ 前端实施

### 1. TypeScript 类型定义
**文件**: `frontend-vue/src/api/types.ts`

**新增类型**:
- `RiskItem`: 风险项结构
- `ExposureItem`: 暴露统计结构
- `PortfolioRiskLensResponse`: API 响应类型

### 2. API Client
**文件**: `frontend-vue/src/api/client.ts`

**新增方法**:
```typescript
async getPortfolioRiskLens(
  sessionId: string, 
  userId: string
): Promise<PortfolioRiskLensResponse>
```

### 3. Vue 组件
**文件**: `frontend-vue/src/components/PortfolioRiskLens.vue`

**功能模块**:
1. **风险评分总览**: 0-100 分值 + 健康度标签（健康/低风险/中等风险/高风险）
2. **集中度风险卡片**: 单一持仓 + 行业集中度
3. **亏损持仓卡片**: 显示所有亏损 >5% 的持仓
4. **过期研究卡片**: 数据截至超过 7/30 天的报告
5. **缺失覆盖卡片**: 高仓位但无研究报告
6. **行业暴露**: 各行业占比统计
7. **币种暴露**: 各币种占比统计（>1 种时显示）
8. **市场暴露**: US/HK/CN 市场占比（>1 个时显示）
9. **推荐操作**: 最多显示 5 条操作建议

**交互**:
- 所有风险项可点击跳转到 `target_route`
- Severity 徽章颜色区分（high/medium/low）
- 刷新按钮手动重载数据

### 4. 路由配置
**文件**: `frontend-vue/src/router/index.ts`

**新增路由**:
```typescript
{
  path: '/portfolio/risk-lens',
  name: 'portfolio-risk-lens',
  component: () => import('@/components/PortfolioRiskLens.vue'),
  meta: { requiresAuth: true }
}
```

---

## ✅ 测试验证

### 1. 单元测试
**文件**: `backend/tests/test_portfolio_risk_lens.py`

**测试覆盖** (9/9 通过):
1. ✅ `test_empty_portfolio` — 空持仓返回空风险透镜
2. ✅ `test_single_position_concentration` — 单一持仓 >25% 触发
3. ✅ `test_sector_concentration` — 行业集中度 >40% 触发
4. ✅ `test_loss_positions` — 亏损 -5% / -10% 分级
5. ✅ `test_stale_research` — 7/30 天过期分级
6. ✅ `test_missing_coverage` — 高仓位无报告覆盖
7. ✅ `test_risk_score_calculation` — 风险评分计算逻辑
8. ✅ `test_exposure_aggregation` — 行业/币种/市场暴露统计
9. ✅ `test_next_actions_generation` — 推荐操作生成

**运行结果**:
```
9 passed in 0.10s
```

### 2. TypeScript 类型检查
**命令**: `npm run typecheck`

**结果**: ✅ 无类型错误

---

## 📊 代码统计

| 文件类型 | 新增文件 | 修改文件 | 总代码行数 |
|---------|---------|---------|-----------|
| 后端 Python | 2 个 | 1 个 | ~450 行 |
| 前端 TypeScript/Vue | 1 个 | 2 个 | ~320 行 |
| 测试文件 | 1 个 | 0 个 | ~180 行 |
| **总计** | **4 个** | **3 个** | **~950 行** |

---

## 🎯 功能亮点

### 1. 规则可配置
所有风险阈值集中在 `RISK_RULES` 字典，未来可支持用户自定义参数。

### 2. 依赖注入模式
路由使用 `RiskLensRouterDeps` 注入依赖，便于测试和解耦。

### 3. 多维度风险分析
不仅关注亏损，还分析集中度、新鲜度、覆盖度，提供全面风险视图。

### 4. 可操作性强
每个风险项带 `target_route`，点击直达相关页面（Dashboard / Reports / Chat）。

### 5. 空态友好
空持仓时返回 `add_portfolio` 建议，引导用户录入数据。

---

## 🔄 后续工作（Day 2-3）

### Day 2: 趋势图准备
1. **数据库设计**: 创建 `portfolio_risk_snapshots` 表
2. **每日快照 Cron**: APScheduler 定时任务（每日 UTC 16:00）
3. **历史查询 API**: `/api/portfolio/risk-lens/history?days=30`

### Day 3: 前端趋势图
1. **Chart.js 集成**: 安装依赖 + 折线图组件
2. **时间序列展示**: risk_score / total_value / concentration 趋势
3. **时间范围选择**: 7天 / 30天 / 90天切换

---

## 🚀 快速验证

### 启动后端
```bash
cd backend
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

### 启动前端
```bash
npm run dev
```

### 访问页面
```
http://localhost:5173/portfolio/risk-lens
```

### 测试 API
```bash
curl "http://localhost:8000/api/portfolio/risk-lens?session_id=test&user_id=default_user" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## 📝 注意事项

1. **身份验证**: 端点需要有效的 JWT token
2. **数据依赖**: 需要先在 Portfolio 和 Report Index 中有数据
3. **币种显示**: 当前仅统计，未做汇率换算
4. **市场识别**: 根据 ticker 后缀推断（.HK / .SS / .SZ），可能不准确

---

## ✅ 验收标准

- [x] 后端规则引擎覆盖 8 条风险规则
- [x] API 端点返回完整风险透镜结构
- [x] 单元测试 9/9 通过
- [x] 前端组件可渲染所有风险模块
- [x] TypeScript 类型检查无错误
- [x] 风险项可点击跳转
- [x] Severity 颜色正确区分

---

**完成状态**: ✅ Day 1 全部完成
**下一步**: Day 2 — 数据库快照 + 定时任务
