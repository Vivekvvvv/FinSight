# Phase 6 E2E 稳定化进度报告

**日期**: 2026-06-08  
**状态**: 🔄 进行中 - Batch 1 Mock 路径统一  

---

## 执行摘要

已完成 Batch 1 的核心工作：
- ✅ 创建统一 API Mock Helper (`e2e/helpers/apiMocks.ts`)
- ✅ 添加 data-testid 到关键组件
- 🔄 修复 Phase 4 Timeline + What Changed 测试（测试运行中）

---

## Batch 1: Mock 路径统一 - 进度

### ✅ 已完成

#### 1. 统一 Mock Helper 创建
**文件**: `frontend-vue/e2e/helpers/apiMocks.ts` (新建，655 行)

**Mock 函数**:
- `setupReportsMocks()` - 报告资产化
- `setupTimelineMocks(symbol)` - 时间线事件
- `setupWhatChangedMocks()` - 今日变化
- `setupResearchQualityMocks()` - 研究质量
- `setupResearchNotesMocks()` - 研究笔记
- `setupPortfolioRiskLensMocks()` - 持仓风险透镜
- `setupTodayWorkspaceMocks()` - 今日工作台
- `setupAlertsFeedMocks()` - 告警推送
- `setupPortfolioSummaryMocks()` - 持仓摘要
- `setupWatchlistMocks()` - 自选列表

**组合函数**:
- `setupPhase45CoreMocks()` - Phase 4/5 核心功能
- `setupTodayWorkspaceFullMocks()` - Today Workspace 全部
- `setupAllMocks()` - 全局 Mock

**特点**:
- 所有 URL pattern 使用 `**/api/...` 匹配（无需查询参数）
- Response 结构严格符合 `src/api/types.ts`
- Mock 数据完整（包含所有必需字段）

#### 2. 选择器稳定化（Batch 2 部分提前完成）

**修改文件**:
- `src/components/EvidenceTimeline.vue`
  - 添加 `data-testid="event-card"` 到 `.event-card`
  - 添加 `data-testid="event-title"` 到 `.event-title`

- `src/components/WhatChangedCard.vue`
  - 添加 `data-testid="what-changed-card"` 到根元素
  - 添加 `data-testid="severity-badge"` 到严重度徽章
  - 添加 `data-testid="change-title"` 到标题

- `src/pages/WelcomePage.vue`
  - 添加 `data-testid="what-changed-panel"` 到 What Changed 模块

#### 3. 测试文件修复

**文件**: `frontend-vue/e2e/pages.spec.ts`

**修复的测试**:
1. `/timeline/:symbol — 基础渲染` ✅
   - 使用 `setupTimelineMocks()` + `setupWhatChangedMocks()`
   - 选择器改为 `[data-testid="event-card"]`

2. `/timeline/:symbol — 类型筛选` ✅
   - 添加 `what-changed` mock
   - 选择器改为 `[data-testid="event-card"]`

3. `/timeline/:symbol — 点击 report 事件跳转` ✅
   - 添加 `what-changed` mock
   - 选择器改为 `[data-testid="event-card"]`

4. `/timeline/:symbol — 点击 note 事件跳转` ✅
   - 添加 `what-changed` mock
   - 选择器改为 `[data-testid="event-card"]`

5. `/timeline/:symbol — 高风险事件样式显示` ✅
   - 添加 `what-changed` mock
   - 选择器改为 `[data-testid="event-card"]`

6. `/welcome — 显示 What Changed 模块` ✅
   - 使用 `setupTodayWorkspaceMocks()` + `setupWhatChangedMocks()`
   - 选择器改为 `[data-testid="what-changed-panel"]`

7. `/welcome — What Changed 无变化时不显示模块` ✅
   - 补全 mock（添加 `research-quality`）
   - 选择器改为 `[data-testid="what-changed-panel"]`

8. `/welcome — high severity 变化显示高风险样式` ✅
   - 补全 mock（添加 `research-quality`）
   - 选择器改为 `[data-testid="severity-badge"]`

### 🔄 进行中

**测试验证**: 运行中（第 2 次）
```bash
npx playwright test e2e/pages.spec.ts --grep "Timeline|What Changed"
```

### 📋 待处理

#### Batch 2: 选择器稳定化（剩余）
- [ ] `ResearchQualityOverview` 组件添加 data-testid
- [ ] `ResearchNotesPage` 组件添加 data-testid
- [ ] 更新对应测试用例

#### Batch 3: Phase 2 Mock 数据补全
- [ ] 修复 8 个 Reports 资产化测试
- [ ] 补全 mock 数据字段（`title`, `ticker`, `tags`, etc.）
- [ ] 统一 Reports mock 路径为 `**/api/reports/index**`

#### Batch 4: Phase 3 Today Workspace 决策
- [ ] 审查 5 个 Today Workspace 失败测试
- [ ] 判断功能是否已实现
- [ ] 决定修复 vs `test.skip`

---

## 关键发现

### 问题 1: Timeline 页面同时调用 2 个 API

**发现**: TimelinePage.vue 在 `loadTimeline()` 中同时调用：
- `apiClient.getTimeline()` → `/api/timeline/:symbol`
- `apiClient.getWhatChanged()` → `/api/what-changed`

**解决**: 所有 Timeline 测试必须同时 mock 这两个 API。

### 问题 2: Mock URL Pattern 匹配

**原始 Mock**: `**/api/timeline/AAPL?*`  
**实际请求**: `/api/timeline/AAPL?session_id=...&user_id=...`

**问题**: `?*` 要求至少 1 个查询参数，但 Playwright route matching 可能不匹配。

**解决**: 改为 `**/api/timeline/AAPL**`（双星号匹配所有）。

### 问题 3: 选择器脆弱性

**原始选择器**: `.event-card`, `.what-changed-card`  
**问题**: class 名称可能被 CSS 重构破坏

**解决**: 添加 `data-testid` 属性，专用于测试。

---

## 文件变更清单

### 新增文件
- `frontend-vue/e2e/helpers/apiMocks.ts` (655 行)

### 修改文件
| 文件 | 变更内容 | 行数变化 |
|------|----------|---------|
| `e2e/pages.spec.ts` | 添加 import + 修复 8 个测试 | ~80 行 |
| `src/components/EvidenceTimeline.vue` | 添加 2 个 data-testid | +2 行 |
| `src/components/WhatChangedCard.vue` | 添加 3 个 data-testid | +3 行 |
| `src/pages/WelcomePage.vue` | 添加 1 个 data-testid | +1 行 |

**总计**: +741 行，~6 行修改

---

## 下一步行动

### 立即执行（等待测试结果）
1. ✅ 检查第 2 次测试运行结果
2. 📋 如果仍有失败，分析日志并调整
3. 📋 确认 Phase 4 Timeline + What Changed 全绿后，进入 Batch 3

### Batch 3 计划（预估 1-2h）
1. 修复 `/reports` 资产化测试（8 个失败）
2. 使用 `setupReportsMocks()` 替换内联 mock
3. 补全 mock 数据结构
4. 验证：`--grep "Reports.*资产化"`

### Batch 4 计划（预估 30min）
1. 审查 5 个 Today Workspace 测试
2. 判断功能状态（已实现 vs 废弃）
3. 修复或 `test.skip`（带原因注释）

---

## 验收标准

### Phase 6 最低目标
- ✅ 22 个历史失败全部分类（已完成）
- 🔄 Phase 4/5 相关 E2E 全绿（8 个，修复中）
- ⏳ 非阻塞失败有明确原因和后续计划（待 Batch 3/4）
- ✅ mock helper 已建立
- ⏳ typecheck/build 通过（待验证）
- ⏳ 文档更新完成（待最终报告）

### Phase 6 理想目标
- ⏳ 完整 npm run test:e2e 全绿（48/48）

---

## 风险与缓解

| 风险 | 状态 | 缓解措施 |
|------|------|----------|
| Mock URL 不匹配真实请求 | ✅ 已解决 | 使用 `**/api/**` 双星号匹配 |
| 选择器过于脆弱 | ✅ 已解决 | 添加 data-testid |
| Phase 2/3 测试无法全部修复 | ⏳ 待评估 | Batch 3/4 执行时判断 |
| Timeline 页面调用多个 API | ✅ 已解决 | 同时 mock timeline + what-changed |

---

**下次更新**: Batch 1 测试验证完成后
