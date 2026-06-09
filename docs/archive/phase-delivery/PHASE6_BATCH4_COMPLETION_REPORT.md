# Phase 6 Batch 4 完成报告

**日期**: 2026-06-08  
**状态**: ✅ **Batch 4 完成 — E2E 全绿 48/48**

---

## 执行摘要

Batch 4 处理了剩余 9 个失败测试（原估计 7 个，实际统计为 9 个）。

**修复成果**：
- ✅ E2E 测试：48/48 通过（从 48 - 9 = 39 通过 → 48 全绿）
- ✅ TypeScript 类型检查：0 错误
- ✅ 构建：6.31s 成功

---

## 失败分析

### 实际剩余失败（9 个）

| # | 测试名 | 根本原因 |
|---|--------|---------|
| 1 | `/welcome — Today Workspace 基础渲染` | 缺少 `what-changed` + `research-quality` mock |
| 5 | `/reports — 列表渲染 + 收藏切换 + MD导出` | 缺少 `research-quality` mock |
| 6 | `/reports — 版本对比面板` | 缺少 `research-quality` mock |
| 22 | `/welcome (Today Workspace) — 空态显示添加入口` | 缺少 `what-changed` + `research-quality` mock |
| 23 | `/welcome (Today Workspace) — 有数据时显示完整模块` | 缺少 `what-changed` + `research-quality` mock |
| 24 | `/welcome (Today Workspace) — 风险持仓显示` | 缺少 `what-changed` + `research-quality` mock |
| 25 | `/welcome (Today Workspace) — 待复查报告标记` | 缺少 `what-changed` + `research-quality` mock |
| 26 | `/welcome (Today Workspace) — NextActions 点击跳转` | 缺少 `what-changed` + `research-quality` mock |
| 43 | `/welcome — 点击变化卡片跳转 target_route` | URL pattern `?*` 不稳定 + 缺少 `research-quality` mock |

### 根本原因模式

**唯一根本原因**：WelcomePage 调用 3 个并发 API（Promise.all），任何一个未 mock → `workspace` 保持 null → 内容区域不渲染。

```typescript
// WelcomePage.vue refresh()
const [workspaceData, changesData, qualityData] = await Promise.all([
  apiClient.getTodayWorkspace(sessionId, userId),    // /api/today
  apiClient.getWhatChanged({ sessionId, userId }),   // /api/what-changed
  apiClient.getResearchQuality({ sessionId, userId}), // /api/research-quality
]);
```

测试只 mock 了 `today`，缺少 `what-changed` 和 `research-quality`。

**同样模式**：ReportsLibraryPage 调用 2 个并发 API，已在 Batch 3 修复，但旧版 `/reports — 列表渲染` 测试没有使用 `setupReportsPageMocks()` helper。

---

## 技术修复

### 新增 helper 函数

```typescript
// e2e/pages.spec.ts — 文件顶部（beforeEach 之后）
function setupWelcomePageCoreMocks(page: Page) {
  page.route('**/api/what-changed**', (r) => json(r, {
    success: true, as_of: new Date().toISOString(), count: 0, items: [],
  }));
  page.route('**/api/research-quality**', (r) => json(r, {
    success: true,
    as_of: new Date().toISOString(),
    summary: {
      total_reports: 0, stale_reports: 0, low_quality_reports: 0,
      blocked_reports: 0, warn_reports: 0, watch_reports: 0,
      reviewed_rate: 0, challenged_conclusions: 0, health_score: 100,
    },
    top_issues: [], next_actions: [],
  }));
}
```

**使用方式**：
```typescript
test('/welcome — Today Workspace 基础渲染', async ({ page }) => {
  await page.route('**/api/today**', (r) => json(r, {...})); // 每个测试自行 mock
  setupWelcomePageCoreMocks(page);  // ← 补全另外 2 个 API
  await page.goto('/welcome');
  // ...
});
```

### URL Pattern 修复

测试 #43 原来使用了不稳定的 `?*` 模式：
```typescript
// 修复前（不稳定）
await page.route('**/api/today?*', ...)
await page.route('**/api/what-changed?*', ...)

// 修复后（稳定）
await page.route('**/api/today**', ...)
await page.route('**/api/what-changed**', ...)
```

### 修复范围（不新增功能）

- 所有修复均为 mock 补全或 URL 模式调整
- 未修改任何 Vue 组件或业务逻辑
- 未使用 `test.skip`（功能均已实现）
- 未新增业务功能

---

## 验证结果

### 完整 E2E 测试：48/48 ✅

```
Running 48 tests using 1 worker
  ✓  1 /welcome — Today Workspace 基础渲染 (786ms)
  ✓  2 /workbench — 晨报 + 任务 + 持仓风险 (1.0s)
  ... (所有 48 个)
  48 passed (59.1s)
```

### TypeScript + Build

```bash
npm run typecheck  # 0 errors
npm run build      # ✓ built in 6.31s
```

---

## 文件变更

| 文件 | 变更 |
|------|------|
| `frontend-vue/e2e/pages.spec.ts` | 新增 `setupWelcomePageCoreMocks()`；在 9 个测试中添加调用；修复 URL 模式 |

净增约 25 行代码。

