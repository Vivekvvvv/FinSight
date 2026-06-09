# Phase 6 E2E 稳定化最终报告

**日期**: 2026-06-08  
**状态**: ✅ **Phase 6 完成 — E2E 全绿 48/48，从 22 失败到 0 失败**

---

## 最终结果

| 指标 | 数值 |
|------|------|
| **初始失败数** | 22 |
| **最终失败数** | **0** |
| **修复率** | **100%** |
| **总测试数** | 48 |
| **通过率** | **48/48** |
| **TypeScript 错误** | 0 |
| **构建时间** | 6.31s |

---

## Batch 执行总结

| Batch | 目标 | 修复数 | 状态 |
|-------|------|--------|------|
| Batch 1 | Phase 4 Timeline + What Changed | 9 个 | ✅ 完成 |
| Batch 2 | 选择器稳定化（data-testid） | 0 个（提前完成） | ✅ 完成 |
| Batch 3 | Phase 2 Reports 资产化 | 8 个 | ✅ 完成 |
| Batch 4 | Phase 3 Today Workspace + 遗留 | 9 个 | ✅ 完成 |
| **总计** | | **26 个**（含新增测试）| ✅ |

> 注：初始 22 失败 + 新增测试 48 总数，最终 0 失败。

---

## 根本原因汇总

所有 22 个失败归结为 **1 种根本原因**：

### 页面多 API 并发调用，测试 mock 不完整

**页面 API 依赖关系**：

| 页面 | 依赖 API | 数量 |
|------|---------|------|
| `WelcomePage` | `today` + `what-changed` + `research-quality` | 3 |
| `TimelinePage` | `timeline/:symbol` + `what-changed` | 2 |
| `ReportsLibraryPage` | `reports/index` + `research-quality` | 2 |

**根因**：页面用 `Promise.all()` 并发请求，任意一个 API 未被 mock → 请求挂起超时 → 内容不渲染。

---

## 技术方案

### 1. 统一 Mock Helper 体系

**文件**：`frontend-vue/e2e/helpers/apiMocks.ts`（657 行）

| 函数 | 用途 |
|------|------|
| `setupTimelineMocks(page, symbol)` | Timeline 事件列表 |
| `setupWhatChangedMocks(page)` | What Changed 变化列表 |
| `setupResearchQualityMocks(page)` | 研究库健康度 |
| `setupReportsMocks(page)` | 报告索引 |
| `setupTodayWorkspaceMocks(page)` | Today Workspace 聚合 |
| `setupPortfolioSummaryMocks(page)` | 持仓摘要 |
| `setupWatchlistMocks(page)` | 自选列表 |
| `setupAlertsFeedMocks(page)` | 告警 feed |

**组合函数**：
```typescript
setupPhase45CoreMocks(page, symbol)   // Timeline 相关
setupTodayWorkspaceFullMocks(page)    // Today Workspace 全部
setupAllMocks(page, symbol)           // 全局
```

### 2. 页面级 Helper 函数

**在 pages.spec.ts 中**：

```typescript
// WelcomePage 所需（3 API）
function setupWelcomePageCoreMocks(page: Page) {
  // what-changed + research-quality
  // 各测试自行 mock today
}

// ReportsLibraryPage 所需（2 API）
function setupReportsPageMocks(page: Page) {
  // reports/index + research-quality
}
```

### 3. URL Pattern 规范

**统一使用双星号**：
```typescript
// ✅ 正确 — 匹配所有路径和查询参数
'**/api/timeline/AAPL**'
'**/api/what-changed**'

// ❌ 错误 — ?* 在某些情况下不稳定
'**/api/timeline/AAPL?*'
'**/api/today?*'
```

### 4. data-testid 添加（Batch 2）

| 组件 | 新增 data-testid |
|------|----------------|
| `EvidenceTimeline.vue` | `event-card`, `event-title` |
| `WhatChangedCard.vue` | `what-changed-card`, `severity-badge`, `change-title` |
| `WelcomePage.vue` | `what-changed-panel` |

---

## 关键发现

### API 契约问题

**Reports API 字段名**：
```typescript
// ❌ 错误（旧版测试）
{ success: true, reports: [...], count: 3 }

// ✅ 正确（API 实际返回）
{ success: true, items: [...], count: 3 }
```

**教训**：Mock 数据必须严格符合 `src/api/types.ts` 接口定义。

### 页面并发加载模式

Phase 4+ 所有页面使用 `Promise.all()` 并发请求，E2E 测试必须 mock **全部**依赖 API：

```typescript
// WelcomePage.vue
const [workspaceData, changesData, qualityData] = await Promise.all([
  apiClient.getTodayWorkspace(sessionId, userId),
  apiClient.getWhatChanged({ sessionId, userId }),
  apiClient.getResearchQuality({ sessionId, userId }),
]);
// 若任何一个未被 mock → workspace.value 保持 null → 内容不显示
```

---

## 后续维护建议

1. **新增页面时**：先检查 `onMounted` 中调用了哪些 API，在 E2E 测试中 mock 全部
2. **新增 API 时**：同步更新 `e2e/helpers/apiMocks.ts`，避免测试遗漏
3. **Mock 数据**：参考 `src/api/types.ts` 确保字段完整
4. **URL Pattern**：始终用 `**/api/path**`，不用 `?*`

---

## 文件变更清单（Phase 6 全程）

### 新增文件（2 个）
- `frontend-vue/e2e/helpers/apiMocks.ts`（657 行）
- `frontend-vue/e2e/helpers/` 目录结构

### 修改文件（4 个）

| 文件 | 主要变更 |
|------|---------|
| `frontend-vue/e2e/pages.spec.ts` | 添加 mock helpers；修复 26 个测试的 mock 设置 |
| `frontend-vue/src/components/EvidenceTimeline.vue` | 添加 data-testid |
| `frontend-vue/src/components/WhatChangedCard.vue` | 添加 data-testid |
| `frontend-vue/src/pages/WelcomePage.vue` | 添加 data-testid |

---

**Phase 6 完成时间**: 2026-06-08  
**验收结论**: ✅ 全部验收标准达成
