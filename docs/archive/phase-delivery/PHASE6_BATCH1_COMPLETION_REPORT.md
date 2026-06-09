# Phase 6 Batch 1 完成报告

**日期**: 2026-06-08  
**状态**: ✅ **Batch 1 完成 - Phase 4 Timeline + What Changed 全绿**  

---

## 执行摘要

✅ **Batch 1: Mock 路径统一** - 已完成

**成果**:
- ✅ Phase 4 Timeline 测试：6/6 通过
- ✅ Phase 4 What Changed 测试：3/3 通过
- ✅ TypeScript 类型检查：0 错误
- ✅ 前端构建：5.71s 成功

**修复的失败测试**:
- 失败 #16-20：Timeline 交互（5 个）→ **全部修复 ✅**
- 失败 #21-22：What Changed 交互（2 个）→ **全部修复 ✅**

**总进度**: 22 → 15 个失败（修复了 7 个，剩余 15 个）

---

## 技术实现

### 1. 统一 API Mock Helper

**文件**: `frontend-vue/e2e/helpers/apiMocks.ts` (655 行)

**核心函数**:
```typescript
// Phase 4 核心
setupTimelineMocks(page, symbol)
setupWhatChangedMocks(page)
setupResearchQualityMocks(page)
setupResearchNotesMocks(page)

// Phase 2 资产化
setupReportsMocks(page)

// Phase 3 Today Workspace
setupTodayWorkspaceMocks(page)
setupPortfolioSummaryMocks(page)
setupWatchlistMocks(page)
setupAlertsFeedMocks(page)

// 其他
setupPortfolioRiskLensMocks(page)
```

**组合函数**:
```typescript
setupPhase45CoreMocks(page, symbol)  // Timeline + WhatChanged + Quality
setupTodayWorkspaceFullMocks(page)   // Today Workspace 全部依赖
setupAllMocks(page, symbol)          // 全局 Mock
```

**特点**:
- URL pattern 使用 `**/api/...`（双星号，无需精确查询参数）
- Response 结构严格符合 `src/api/types.ts`
- Mock 数据完整（所有必需字段 + 合理默认值）

### 2. 选择器稳定化（Batch 2 部分提前完成）

**修改组件**:

#### EvidenceTimeline.vue
```vue
<div class="event-card" data-testid="event-card">
  <h4 class="event-title" data-testid="event-title">{{ event.title }}</h4>
</div>
```

#### WhatChangedCard.vue
```vue
<div class="what-changed-card" data-testid="what-changed-card">
  <div class="severity-badge" data-testid="severity-badge">
    {{ severityText }}
  </div>
  <h3 class="title" data-testid="change-title">{{ item.title }}</h3>
</div>
```

#### WelcomePage.vue
```vue
<div class="panel what-changed-panel" data-testid="what-changed-panel">
  <h2>今日重要变化</h2>
  <WhatChangedCard v-for="item in whatChanged" :key="item.id" :item="item" />
</div>
```

**原则**:
- `data-testid` 仅用于 E2E 测试定位
- 不影响业务逻辑和样式
- class 名称保留（用于 CSS）

### 3. 测试修复策略

**问题 1**: Timeline 页面同时调用 2 个 API

**发现**:
```typescript
// TimelinePage.vue loadTimeline()
const [timelineResp, changesResp] = await Promise.all([
  apiClient.getTimeline({ symbol, sessionId, userId }),
  apiClient.getWhatChanged({ sessionId, userId, symbol }),
]);
```

**解决**: 所有 Timeline 测试必须同时 mock 两个 API
```typescript
test('/timeline/:symbol — 基础渲染', async ({ page }) => {
  setupTimelineMocks(page, 'AAPL');
  setupWhatChangedMocks(page);  // ← 必须添加
  await page.goto('/timeline/AAPL');
  // ...
});
```

**问题 2**: WelcomePage 同时调用 3 个 API

**发现**:
```typescript
// WelcomePage.vue refresh()
const [workspaceData, changesData, qualityData] = await Promise.all([
  apiClient.getTodayWorkspace(sessionId, userId),
  apiClient.getWhatChanged({ sessionId, userId }),
  apiClient.getResearchQuality({ sessionId, userId }),
]);
```

**解决**: What Changed 测试必须 mock 全部 3 个 API
```typescript
test('/welcome — 显示 What Changed 模块', async ({ page }) => {
  setupTodayWorkspaceMocks(page);
  setupWhatChangedMocks(page);
  setupResearchQualityMocks(page);  // ← 必须添加
  await page.goto('/welcome');
  // ...
});
```

**问题 3**: Mock URL 匹配策略

**原始**: `**/api/timeline/AAPL?*`（要求至少 1 个查询参数）  
**实际请求**: `/api/timeline/AAPL?session_id=...&user_id=...`  
**问题**: Playwright route matching 可能不匹配

**解决**: 改为 `**/api/timeline/AAPL**`（双星号匹配所有）
```typescript
// 正确的 mock pattern
page.route('**/api/timeline/AAPL**', async (route) => { ... });
page.route('**/api/what-changed**', async (route) => { ... });
```

---

## 测试结果

### Phase 4 Timeline 测试 (6/6 ✅)

```
✓ /timeline/:symbol — 基础渲染 (1.2s)
✓ /timeline/:symbol — 空态显示 (2.9s)
✓ /timeline/:symbol — 类型筛选 (1.1s)
✓ /timeline/:symbol — 点击 report 事件跳转 (1.3s)
✓ /timeline/:symbol — 点击 note 事件跳转 (1.1s)
✓ /timeline/:symbol — 高风险事件样式显示 (932ms)
```

**修复前**: 5/6 失败（失败 #16-20）  
**修复后**: 6/6 通过 ✅

### Phase 4 What Changed 测试 (3/3 ✅)

```
✓ /welcome — 显示 What Changed 模块 (937ms)
✓ /welcome — What Changed 无变化时不显示模块 (979ms)
✓ /timeline/:symbol — 显示 symbol 相关变化 (914ms)
```

**修复前**: 2/3 失败（失败 #21-22）  
**修复后**: 3/3 通过 ✅

### 验证命令

```bash
# Phase 4 核心测试
npx playwright test e2e/pages.spec.ts --grep "Timeline|What Changed"
# 结果: 9 passed (14.1s)

# TypeScript 类型检查
npm run typecheck
# 结果: 0 errors

# 前端构建
npm run build
# 结果: ✓ built in 5.71s
```

---

## 文件变更清单

### 新增文件 (1 个)
- `frontend-vue/e2e/helpers/apiMocks.ts` (655 行)

### 修改文件 (4 个)

| 文件 | 变更内容 | 行数变化 |
|------|----------|---------|
| `e2e/pages.spec.ts` | 添加 import + 修复 9 个测试 | +30, -80 |
| `src/components/EvidenceTimeline.vue` | 添加 2 个 data-testid | +2 |
| `src/components/WhatChangedCard.vue` | 添加 3 个 data-testid | +3 |
| `src/pages/WelcomePage.vue` | 添加 1 个 data-testid | +1 |

**总计**: +691 行，-80 行，净增 +611 行

---

## 经验总结

### ✅ 成功经验

1. **集中式 Mock 管理**
   - 单一 `apiMocks.ts` 文件管理所有 mock
   - 避免测试文件中重复 `page.route`
   - 提高可维护性和复用性

2. **组合函数策略**
   - `setupPhase45CoreMocks()` 一次性 mock 多个相关 API
   - 减少测试代码重复
   - 明确依赖关系

3. **data-testid 原则**
   - 只添加测试钩子，不改业务逻辑
   - class 名称保留（用于样式）
   - 语义化命名（`event-card`, `severity-badge`）

4. **渐进式修复**
   - 先修复 Phase 4 核心功能（P1 优先级）
   - 验证通过后再进入 Phase 2/3（P2 优先级）
   - 避免"一锅粥"

### ⚠️ 注意事项

1. **页面多 API 依赖**
   - TimelinePage 调用 2 个 API（timeline + what-changed）
   - WelcomePage 调用 3 个 API（today + what-changed + research-quality）
   - 测试必须 mock 全部依赖 API

2. **Mock URL Pattern**
   - 使用 `**/api/path**` 双星号匹配
   - 避免 `?*` 查询参数匹配（不稳定）
   - Playwright route matching 对 glob 敏感

3. **Response 结构严格性**
   - 必须符合 `src/api/types.ts` 接口定义
   - 缺少必需字段会导致前端逻辑错误
   - 使用 TypeScript 类型推断验证

---

## 剩余工作

### Batch 2: 选择器稳定化（剩余部分）

**待添加 data-testid**:
- `ResearchQualityOverview.vue` — 健康度模块
- `ResearchNotesPage.vue` — 笔记页面
- `ReportsLibraryPage.vue` — 报告库页面

**预估**: 30min - 1h

### Batch 3: Phase 2 Mock 数据补全

**待修复测试** (8 个):
- 失败 #6-15：Reports 资产化功能

**问题**:
- Mock 数据字段缺失（`title`, `ticker`, `tags`, etc.）
- Mock 路径不匹配（`**/api/reports?*` vs `/api/reports/index`）

**策略**:
- 使用 `setupReportsMocks()` 替换内联 mock
- 补全 `REPORTS_ASSET` mock 数据结构
- 验证：`--grep "Reports.*资产化"`

**预估**: 1-2h

### Batch 4: Phase 3 Today Workspace 决策

**待处理测试** (5 个):
- 失败 #1-5：Today Workspace 功能

**问题**:
- 功能未实现 vs 测试过期

**策略**:
- 审查功能状态（已实现 vs 废弃）
- 修复测试（如果功能存在）
- `test.skip`（如果功能废弃，带原因注释）

**预估**: 30min

---

## 下一步行动

### 立即执行
1. ✅ Batch 1 完成报告（本文档）
2. 📋 开始 Batch 3：修复 Phase 2 Reports 测试
3. 📋 使用 `setupReportsMocks()` + 补全 mock 数据

### 验收标准（Phase 6 最低目标）
- ✅ 22 个历史失败全部分类
- ✅ Phase 4/5 相关 E2E 全绿（9/9 通过）
- ⏳ 非阻塞失败有明确原因（待 Batch 3/4）
- ✅ mock helper 已建立
- ✅ typecheck/build 通过
- ⏳ 文档更新完成（待最终报告）

---

## 附录

### A. Mock 数据示例

**Timeline Mock**:
```typescript
{
  success: true,
  symbol: 'AAPL',
  count: 2,
  events: [
    {
      id: 'evt_001',
      symbol: 'AAPL',
      event_type: 'report',
      title: 'AAPL Q4 财报更新',
      summary: '财报已发布，营收超预期。',
      occurred_at: '2024-11-10T14:30:00Z',
      severity: 'high',
      source: 'report:rep_googl_001',
      target_route: '/reports?report_id=rep_googl_001',
      evidence: {
        confidence: 0.85,
        citation_count: 10,
        freshness_status: 'live',
        quality_state: 'ok',
      },
    },
    // ...
  ],
}
```

**What Changed Mock**:
```typescript
{
  success: true,
  as_of: '2024-11-15T09:00:00Z',
  count: 2,
  items: [
    {
      id: 'chg_001',
      symbol: 'NVDA',
      change_type: 'report',
      title: 'NVDA 优先级上升',
      severity: 'high',
      reason: '新财报质量改善',
      target_route: '/dashboard/NVDA',
      evidence: {
        quality_state: 'ok',
        freshness_status: 'live',
        citation_quality: 'high',
      },
    },
    // ...
  ],
}
```

### B. 修复命令清单

```bash
# 1. 创建 mock helper
# 手动创建: frontend-vue/e2e/helpers/apiMocks.ts

# 2. 添加 data-testid
# 手动编辑组件文件

# 3. 修复测试
# 手动编辑: frontend-vue/e2e/pages.spec.ts

# 4. 验证 Phase 4
npx playwright test e2e/pages.spec.ts --grep "Timeline|What Changed"

# 5. 验证构建
npm run typecheck
npm run build
```

---

**报告完成时间**: 2026-06-08  
**下一个 Batch**: Batch 3 - Phase 2 Mock 数据补全
