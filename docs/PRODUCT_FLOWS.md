# FinSight 用户任务流（Product Flows）

> 本文件描述 FinSight 当前**真实**的核心用户任务流（基于现有代码与 API），不是产品规划。每条流程标注入口、用户动作、系统响应、成功状态、失败状态。后续 IA 重构若改变入口/路径，需同步更新本文件。

最后核对日期：2026-05-13。后端 entry：`POST /chat/supervisor` SSE，前端 entry：`/welcome` → `EntryGuard` → 主工作区。

---

## 流程清单

| # | 名称 | 主入口 | 主要后端依赖 |
|---|---|---|---|
| 1 | 添加自选股 | Sidebar"我的关注" + Dashboard 顶部 Watchlist | `POST /api/user/watchlist/add` / `remove`、`POST /chat/supervisor` 触发实时报价 |
| 2 | 查看 Dashboard | Sidebar"仪表盘" + Watchlist 点击 | `GET /api/dashboard?symbol=...`、`/insights` |
| 3 | 发起深度研究（对话） | Sidebar"智能对话" + ChatInput | `POST /chat/supervisor` SSE（output_mode=brief / investment_report） |
| 4 | 生成投资报告 | ChatInput 模式切换"深度报告" + Workbench 触发 | `POST /chat/supervisor` SSE + `GET /api/reports/index/replay` |
| 5 | 设置提醒 | Sidebar"订阅管理" + 对话内"alert me when..." | `POST /api/subscriptions`、Chat 中 alert_extractor 节点 |
| 6 | 查看组合晨报（Morning Brief） | Workbench → Morning Brief 卡片 | `POST /api/morning-brief` + Portfolio API |
| 7 | 管理持仓组合 | `/portfolio` 独立页 + CSV 导入 | `GET /api/portfolio/summary`、`POST /api/portfolio/positions`、`PUT /api/portfolio/positions/{ticker}` |

---

## 流程 1：添加自选股

| 阶段 | 内容 |
|---|---|
| **入口** | 1) `Sidebar` 底部"我的关注"列表的 ➕ 按钮；2) `Dashboard` 顶部 `<Watchlist>` 组件（暂未在所有 Dashboard 视图露出） |
| **用户动作** | 在输入框输入股票代码（如 `AAPL`、`600519.SS`、`0700.HK`），回车或点确认 |
| **系统响应** | 前端 `useDashboardStore.addWatchItemApi(ticker)` → 调 `POST /api/user/watchlist/add` → 后端 `services/memory.py` 更新 `data/memory/{user_id}.json` → 前端拉新报价 `GET /api/stock-price/:symbol`（60s 轮询） |
| **成功状态** | Sidebar 列表新增一行，显示 ticker + 实时价格 + 涨跌色（绿涨红跌）；点击行可跳到 `/dashboard/:symbol` |
| **失败状态** | 报错路径：(a) Ticker 无效 → toast "添加失败：未识别的代码"；(b) 服务端 5xx → toast "添加失败：服务暂时不可用"；(c) 报价拉取失败 → 行显示但价格为 `--`，60s 后重试 |

**当前已知缺口**：无分组 / 标签 / 备注；无批量导入；移动端仅展开后可见。

---

## 流程 2：查看 Dashboard

| 阶段 | 内容 |
|---|---|
| **入口** | 1) Sidebar"仪表盘"导航（需有 fallback symbol，否则弹 toast）；2) 关注列表点击；3) Chat 中点 ticker 内联跳转 |
| **用户动作** | 选定 symbol 后浏览 6 个 Tab：Overview / Financial / Technical / News / Peers / Research |
| **系统响应** | `useDashboardData(symbol)` 拉 `GET /api/dashboard?symbol=...`（含 16 个 TTL 分类的缓存），`useDashboardInsights(symbol)` 拉 `GET /api/dashboard/insights`（5 个 Scorer 卡片，1-3s 出结果，无 LLM 时降级到确定性评分） |
| **成功状态** | 6 个 Tab 各自渲染：K 线 + 技术指标 / 8 季财报 / Peers 对比 / 新闻列表 / Research 多 Agent 段落 / 顶部 ScoreRing + FearGreed + RiskMetrics |
| **失败状态** | (a) 无 symbol → 顶部空状态 "请先选择标的"；(b) 单 Tab 数据缺失 → Skeleton 后显示 "数据暂不可用 (源: yfinance/FMP/...)" + Retry；(c) 整页 5xx → 顶部红条 + Retry 按钮 |

**当前已知缺口**：Tab 切换时无 URL 锚点（刷新回 Overview）；Watchlist 在 Dashboard 顶部与 Sidebar 同时存在但状态同步隐式。

---

## 流程 3：发起深度研究（对话）

| 阶段 | 内容 |
|---|---|
| **入口** | Sidebar"智能对话" → `/chat`；或 Dashboard NewsCard 的"问这条"跳转 |
| **用户动作** | 在 ChatInput 输入问题（如 "AAPL 估值如何"），选择 `brief` 模式 + 可选 Persona（中立 / 价值 / 宏观 / 短线） |
| **系统响应** | `POST /chat/supervisor` SSE → LangGraph 18-node pipeline：`build_initial_state` → `parse_operation`（14-level 意图分类）→ `policy_gate` → `planner`（或 `planner_stub`）→ `execute_plan`（最多 3 组并行 agent）→ `synthesize`（冲突检测 + 幻觉清洗）→ `render` |
| **成功状态** | 对话流出现 user message + assistant message（含 markdown + `<chart>` / `<chart_ref>` 内联图表 + 引用链接）；右侧 ExecutionPanel 显示阶段进度（user/expert/dev 三视图）；执行完成后 ChatHistorySidebar 更新会话标题与时间 |
| **失败状态** | (a) LLM 超时 → 切到 stub planner，输出"基于规则推断"水印；(b) 多 Agent 失败 → 仍输出已成功 agent 的合成；(c) Quality Gate block → 返回结构化"质量未达发布门槛"原因 |

**当前已知缺口**：会话历史持久化 50 条上限；无对话搜索；无导出为 markdown（PDF 已有但是按对话整段）。

---

## 流程 4：生成投资报告

| 阶段 | 内容 |
|---|---|
| **入口** | 1) ChatInput 模式切换为"深度报告" → 自动触发 deep_research 路径；2) Workbench 任务下发；3) Dashboard Research Tab 内 "生成深度报告" 按钮 |
| **用户动作** | 输入 ticker 与可选指引（如 "重点关注催化剂与风险"），可选 Persona |
| **系统响应** | 与流程 3 同链路，但 `output_mode=investment_report` 走全套 7 Research Agent 并行 + Synthesize Node + Conflict Detection + Hallucination Scrub + `report_builder`；report 写入 `report_index` SQLite |
| **成功状态** | `<ReportView>` 渲染含：执行摘要 / 核心发现 / 多 Agent 段落 / 冲突矩阵 / 引用列表 / 数据时间标识 / Persona Badge；右上"导出 PDF"按钮可直接下载；Quality Score 显示 pass / warn / block |
| **失败状态** | (a) Quality block → 报告标记"已拦截"，不进入 Library；(b) 部分 agent 失败 → 报告标注 "1 个 Agent 数据不可用"；(c) Plan 拒绝 → 返回理由（如 "建议先添加 ticker"） |

**当前已知缺口**：报告版本对比、收藏、批注、基于新事件刷新旧报告 — 均未实现（阶段 3 任务）。

---

## 流程 5：设置提醒

| 阶段 | 内容 |
|---|---|
| **入口** | 1) Sidebar"订阅管理" → SubscribeModal；2) Chat 内自然语言（"alert me when AAPL drops below 180" → alert_extractor 节点）；3) WorkspaceShell 右侧面板 SubscribeButton |
| **用户动作** | 填写邮箱 + 选 ticker + 选择 alert_type（price_change / price_target / news / risk）+ 阈值 |
| **系统响应** | `POST /api/subscriptions` → `services/subscription_service.py` 原子写 `data/subscriptions.json` → `services/alert_scheduler.py` 在下一个调度周期（15/30/60 min）开始扫描；命中条件后发 SMTP 邮件 |
| **成功状态** | toast "已创建提醒"；Sidebar"订阅管理"右侧角标显示当前订阅数；后续命中条件时邮箱收到 HTML 模板邮件 |
| **失败状态** | (a) SMTP 未配置 → 后端返回 503 "Email service unavailable"，订阅仍保存但不会发邮件；(b) 邮件连续 3 次永久失败 → 后端自动 disable 该订阅并 toast 提示 |

**当前已知缺口**：无独立 Alerts 历史页面；订阅列表与历史告警混杂在 modal 内；无 in-app 通知（仅邮件）。

---

## 流程 6：查看组合晨报（Morning Brief）

| 阶段 | 内容 |
|---|---|
| **入口** | Workbench → Morning Brief 卡片 → "生成今日晨报"按钮 |
| **用户动作** | 点击按钮（不需要参数；自动读取当前 user 的 portfolio + watchlist） |
| **系统响应** | `POST /api/morning-brief` → 复用 LangGraph Pipeline 进入 morning_brief 模式 → 确定性合成（零 LLM 成本）→ 输出包含：持仓变化 / 相关新闻 / 风险提示 / 今日关注事项 |
| **成功状态** | 卡片渲染分段：📊 持仓概览（总市值 + 主要仓位） / 📰 相关新闻（合并 watchlist + portfolio）/ ⚠️ 风险提示（来自 RiskAgent）/ 📅 今日关注（earning / event 日历） |
| **失败状态** | (a) Portfolio 为空 → 卡片显示"请先添加持仓"+ 跳转链接；(b) 行情失败 → 持仓部分降级为 "数据部分不可用"；(c) Pipeline 异常 → 整卡显示 retry 按钮 |

**当前已知缺口**：无历史 Brief 列表（阶段 1 任务 18）；无定时推送（用户必须主动触发）；移动端布局未优化。

---

## 流程 7：管理持仓组合

| 阶段 | 内容 |
|---|---|
| **入口** | `/portfolio` 独立页；Command Palette 的"打开持仓组合"；未来可从 Dashboard Portfolio 面板跳转 |
| **用户动作** | 查看现有持仓；编辑 `shares / avg_cost / name / tags / note`；或上传 CSV，格式为 `ticker,shares,avg_cost,name,tags,note` |
| **系统响应** | `GET /api/portfolio/summary` 拉取持仓与估值；单条编辑走 `PUT /api/portfolio/positions/{ticker}`；CSV 导入解析后与当前持仓合并，调用 `POST /api/portfolio/positions` bulk sync。后端校验 `shares >= 0` 与 `avg_cost >= 0` |
| **成功状态** | 页面展示总市值/成本/盈亏摘要，持仓卡片显示 ticker、名称、标签、备注、成本与市值；CSV 导入后 toast 显示导入条数并刷新列表 |
| **失败状态** | (a) CSV 缺少 ticker/shares → toast "CSV 导入失败"；(b) shares 或 avg_cost 为负数 → 前端拦截，后端也返回 422；(c) 行情失败 → 仍以成本价或 unavailable 降级展示 |

**当前已知缺口**：无交易流水、无多币种汇总、无 CSV 导出，成本价仍是持仓级平均成本而非逐笔 lot。

---

## 跨流程通用契约

- **数据时效性**：所有展示数据如带 `last_updated` / `retrieved_at`，需在 UI 上明确显示；缺失时显示 "更新时间未知"，**禁止伪造时间**。
- **AI 输出分层**（阶段 2 强制）：报告与 AI Insight 卡片必须区分：事实（来自工具/Filing/News）/ AI 推断（合成结论）/ 风险（与置信度共显）/ 待验证（无证据支撑的猜测必须标红）。
- **免责声明**：Chat、Report、Rebalance 建议出口处必须显示统一"非投资建议"声明，由 `<Disclaimer>` 组件统一渲染（阶段 2 任务 26）。
- **可观测性**：每个 AI 输出在 Trace 三视图（user / expert / dev）下均可还原其 plan / step / evidence 路径。

---

## 后续规划交叉引用

| 流程 | 待补能力 | 阶段任务编号 |
|---|---|---|
| 1 | 自选股分组 / 标签 / 备注 | Phase 1, T10-T12 |
| 2 | URL 锚点持久化、Tab deep-link | Phase 0 IA 重构后补 |
| 3 | 对话搜索、导出 markdown | Phase 3 |
| 4 | 报告版本对比 / 收藏 / 旧报告刷新 | Phase 3, T30-T32 |
| 5 | Alerts 独立页面 + 历史 | Phase 0 IA 重构 + Phase 4 gate |
| 6 | 晨报历史 + 定时推送 | Phase 1, T18 |
| 7 | 多币种 / 交易流水 / CSV 导出 | Phase 1 后续 |

变更时请同步 `docs/PRODUCT_BASELINE.md`。
