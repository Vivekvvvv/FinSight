# FinSight 用户任务流（当前 7 入口版）

> 本文件描述 FinSight 当前真实用户任务流，入口以 `frontend-vue/src/router/index.ts` 和 `frontend-vue/src/components/AppShell.vue` 为准。FinSight 只提供研究复查建议，不提供买入、卖出、持有、目标价、仓位或收益承诺。

最后核对日期：2026-06-29。当前主线：`frontend-vue -> FastAPI`。

## 1. 当前核心入口

| # | 页面 | 路由 | 主要用途 | 主要后端依赖 |
|---|---|---|---|---|
| 1 | 今日工作台 | `/welcome` | 每日研究入口、待复查事项、数据源/系统状态抽屉 | `/api/today`、`/api/what-changed`、`/api/research-quality`、`/api/data-sources/status` |
| 2 | 标的研究 | `/dossier/:symbol` | 单个标的的行情、K 线、AI 洞察、时间线、报告、笔记聚合 | `/api/dashboard*`、`/api/quote/*`、`/api/kline/*`、`/api/timeline/*` |
| 3 | 股票发现 | `/stocks` | 筛选候选股、自选、A 股市场工具 | `/api/screener/*`、`/api/user/watchlist/*`、A 股工具接口 |
| 4 | 组合管理 | `/portfolio` | 持仓摘要、持仓维护、风险镜头、组合工具 | `/api/portfolio/*`、`/api/portfolio/risk-lens`、`/api/backtest`、`/api/rebalance` |
| 5 | 报告库 | `/reports` | 报告列表、报告详情、生成报告、财报分析入口 | `/api/reports/index`、`/api/reports/replay/*`、研究报告接口 |
| 6 | 研究笔记 | `/notes` | Markdown 笔记、图片、ticker 筛选和证据沉淀 | `/api/research-notes*` |
| 7 | AI 助手 | `/chat` | 智能问答、深度研究、流式执行轨迹、会话记忆 | `/chat/supervisor/stream`、`/api/chat/history` |

## 2. 旧 URL 收口规则

| 旧入口 | 当前去向 | 说明 |
|---|---|---|
| `/workbench` | `/welcome` | 今日任务、持仓风险、近期报告已并入今日工作台 |
| `/dashboard/:symbol` | `/dossier/:symbol` | Dashboard 后端 API 仍作为标的页数据层使用，页面体验并入 Dossier |
| `/research/qa` | `/chat?mode=qa` | 智能问答并入 AI 助手 |
| `/research/report/:ticker?` | `/reports?tool=generate&ticker=...` | 生成报告并入报告库 |
| `/research/financials` | `/reports?tool=financials` | 财报分析并入报告库 |
| `/portfolio/optimize` | `/portfolio?tool=optimize` | 组合优化并入组合工具 |
| `/backtest` | `/portfolio?tool=backtest` | 回测并入组合工具 |
| `/watchlist` | `/stocks?tab=watchlist` | 自选管理下沉到股票发现 |
| `/alerts` | `/welcome` | 提醒高频内容下沉到今日工作台 |
| `/data-sources` | `/welcome?drawer=data` | 数据源状态进入右上角上下文抽屉 |
| `/system/health` | `/welcome?drawer=system` | 系统状态进入右上角上下文抽屉 |
| `/top-list`、`/north-flow`、`/margin-trading` | `/stocks?tool=...` | A 股市场工具并入股票发现 |

## 3. 关键用户流程

### 流程 A：每日复查

| 阶段 | 内容 |
|---|---|
| 入口 | 打开 `/welcome` |
| 用户动作 | 查看今日摘要、What Changed、研究质量、待复查报告和下一步动作 |
| 系统响应 | 聚合 Today Workspace、What Changed、Research Quality、Portfolio/Watchlist 上下文 |
| 成功状态 | 用户能从卡片直接进入标的、报告、组合或笔记继续复查 |
| 失败状态 | 后端未启动或数据源不可用时显示统一 loading/error/empty 状态，并提示检查本地后端或数据源配置 |

### 流程 B：研究一个标的

| 阶段 | 内容 |
|---|---|
| 入口 | `/dossier/AAPL`，或从今日工作台、股票发现、报告、笔记跳入 |
| 用户动作 | 查看行情、K 线、财务、新闻、AI 洞察、时间线和关联研究资产 |
| 系统响应 | 调用 Dashboard 兼容 API、行情 API、Timeline、Report Index、Research Notes |
| 成功状态 | 页面明确显示数据来源、更新时间和可复查证据 |
| 失败状态 | 单块数据失败时降级展示，不阻断整个标的页；全页失败时显示可重试提示 |

### 流程 C：发现候选股并沉淀为研究对象

| 阶段 | 内容 |
|---|---|
| 入口 | `/stocks` |
| 用户动作 | 设置筛选条件、翻页查看候选、打开 A 股市场工具、加入自选或进入标的页 |
| 系统响应 | `POST /api/screener/run` 返回候选；A 股工具展示龙虎榜、北向资金、融资融券等下沉能力 |
| 成功状态 | 用户可把候选加入 watchlist、创建初始笔记或进入 `/dossier/:symbol` |
| 失败状态 | 筛选接口失败时展示中文可行动错误；工具按钮有 loading/disabled 状态，避免“点了没反应” |

### 流程 D：管理组合与风险

| 阶段 | 内容 |
|---|---|
| 入口 | `/portfolio` |
| 用户动作 | 查看持仓摘要、编辑持仓、查看风险镜头、打开组合工具 |
| 系统响应 | 读取 Portfolio Summary、Risk Lens、Backtest、Rebalance 相关接口 |
| 成功状态 | 持仓和风险信息能形成下一步复查动作，并可跳回标的页或报告库 |
| 失败状态 | 组合为空时显示空状态；行情失败时保留成本视角并标出数据不可用 |

### 流程 E：生成和复查报告

| 阶段 | 内容 |
|---|---|
| 入口 | `/reports` |
| 用户动作 | 浏览报告库、打开报告详情、生成报告、进入财报分析 |
| 系统响应 | 读取 Report Index 和 Replay；生成报告时复用 LangGraph 深度研究链路 |
| 成功状态 | 报告展示引用、质量状态、更新时间和相关标的，可回跳 Dossier |
| 失败状态 | 无报告时显示空状态；生成失败时展示失败原因，不伪造成完整报告 |

### 流程 F：沉淀研究笔记

| 阶段 | 内容 |
|---|---|
| 入口 | `/notes` |
| 用户动作 | 创建 Markdown 笔记、上传图片、按 ticker 或关键词筛选 |
| 系统响应 | 调用 Research Notes CRUD、图片接口，并把笔记纳入时间线/标的研究资产 |
| 成功状态 | 笔记可作为后续 Dossier、Timeline 和 AI 问答的证据上下文 |
| 失败状态 | 上传或保存失败时保留用户输入，并显示可重试错误 |

### 流程 G：向 AI 助手提问

| 阶段 | 内容 |
|---|---|
| 入口 | `/chat` 或 `/research/qa` redirect |
| 用户动作 | 输入研究问题，可在智能问答/报告模式之间切换 |
| 系统响应 | SSE 流式执行 LangGraph，展示 token、执行轨迹、证据和最终回答 |
| 成功状态 | 回答保持“研究复查建议”语义，并更新会话上下文记忆 |
| 失败状态 | LLM 或工具失败时返回可理解错误；部分 agent 失败时尽量保留已成功证据并标记降级 |

## 4. 跨流程契约

- 数据来源必须明确标注 `live`、`fallback`、`cached`、`demo` 或 `stale`，禁止把 demo 数据伪装为实时行情。
- AI 输出必须区分事实、推断、风险和待验证内容。
- 旧 URL 不直接 404，统一 redirect 到当前所属页面。
- 所有异步按钮必须有 loading/disabled 反馈。
- 空状态要告诉用户下一步可以做什么，而不是只显示“暂无数据”。
- 本地运行数据、日志、截图、缓存和 `backend/data/` 不进入提交。
