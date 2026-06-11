# FinSight AI

FinSight AI 是一个基于 **Vue 3 + FastAPI** 的证据驱动金融研究工作台。它的目标不是给出买卖建议，而是帮助个人研究者每天快速回答：

- 今天发生了什么变化？
- 这个变化为什么重要？
- 它影响哪个标的、报告、风险项、提醒或研究笔记？
- 我下一步应该去哪里复查证据？

本项目不面向商业化发布，定位是个人研究闭环和 AI-native 产品工程实践。

## 当前主线

```text
浏览器
  -> frontend-vue  (Vue 3 + Vite + ECharts)
  -> backend       (FastAPI + 研究服务 + 可选 LLM/RAG)
  -> 本地数据 / Docker PostgreSQL
```

旧 React 前端和 Spring 迁移实验已经退出当前运行链路，不再作为默认架构的一部分。

## 核心能力

- **Today Workspace**：每日研究入口，聚合持仓、自选、提醒、待复查报告和下一步动作。
- **Dashboard**：高信息密度标的分析页，包含行情、图表、技术面、估值、情绪、风险、新闻和 AI 洞察。
- **Chat Research Console**：流式研究对话，展示执行过程、报告模式、证据面板和 Markdown 导出。
- **Portfolio Risk Lens**：持仓风险评分、集中度提示、趋势快照和复查路径。
- **Research Notebook**：Markdown 研究笔记，支持图片上传、ticker 筛选、搜索、软删除和时间线接入。
- **Evidence Timeline**：统一事件流，聚合报告、提醒、笔记、风险和自选标的变化。
- **What Changed**：规则化识别今日重要变化，按严重度、时效性和关联度排序。
- **Research Quality**：研究库健康度、过期报告、低引用报告、未复查项目和被新证据挑战的旧结论。

## Git 历史说明

早期开发主要发生在本地工作区和 AI Agent 会话中，原始 Git 历史没有完整、干净地保留。为了避免把本地运行数据、个人信息、会话摘要或疑似密钥痕迹带入仓库，本项目采用从今天开始重建的干净本地历史。

真实项目演进不靠伪造 commit 日期记录，而是通过 [`docs/PROJECT_TIMELINE.md`](./docs/PROJECT_TIMELINE.md) 用“证据来源 + 日期可信度”的方式说明。

## 本地启动

### 后端

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn backend.api.main:app --reload --host 127.0.0.1 --port 8000
```

### 前端

```powershell
cd frontend-vue
npm install
npm run dev
```

打开终端输出的 Vite 地址即可。开发环境下前端默认连接 `127.0.0.1:8000`。

## 配置

复制示例配置后填入本地值：

```powershell
Copy-Item .env.example .env
Copy-Item .env.server.example .env.server
```

真实密钥不要提交。生产可用前至少需要配置：

- `JWT_SECRET`
- `API_AUTH_KEYS`
- 有效的 `OPENAI_COMPATIBLE_API_KEY` 或兼容 LLM 服务密钥

发布阻塞项见 [`docs/RELEASE_READINESS.md`](./docs/RELEASE_READINESS.md)。

### Demo Mode

没有真实行情、FMP、LLM 或生产密钥时，可以打开 Demo Mode：

```powershell
$env:FINSIGHT_DEMO_MODE="true"
python -m uvicorn backend.api.main:app --reload --host 127.0.0.1 --port 8000
```

Demo Mode 会在真实数据为空时返回只读示例数据，保证 `/welcome`、`/portfolio`、`/reports`、`/notes`、`/timeline` 等核心页面可以完整展示研究闭环。状态接口：

```text
GET /api/demo/status
```

返回当前是否启用 Demo、数据来源和缺失的真实服务配置。

## 状态口径

- **本地 Demo 体验**：`READY`。无需真实密钥即可查看主要页面和研究闭环。
- **本地真实数据体验**：`READY_WITH_NOTES`。取决于行情、LLM、RAG 等外部服务配置。
- **生产发布**：`READY_WITH_BLOCKERS`。只有 `JWT_SECRET`、`API_AUTH_KEYS`、有效 LLM key 和外部 smoke 全部确认后，才升级为 `READY`。

## 验证命令

```powershell
python -m pytest -q
cd frontend-vue
npm run typecheck
npm run build
npm run test:e2e
```

历史验证中，Phase 6/7 已经达到 48/48 E2E 全绿，核心后端测试通过。

## 文档入口

- [`docs/DOCS_INDEX.md`](./docs/DOCS_INDEX.md)：文档索引。
- [`docs/DELIVERY_OVERVIEW.md`](./docs/DELIVERY_OVERVIEW.md)：Phase 4-9 交付总览。
- [`docs/PROJECT_TIMELINE.md`](./docs/PROJECT_TIMELINE.md)：证据化项目时间线。
- [`docs/RELEASE_READINESS.md`](./docs/RELEASE_READINESS.md)：发布就绪状态与阻塞项。
- [`docs/API_CONTRACT_CURRENT.md`](./docs/API_CONTRACT_CURRENT.md)：当前核心 API 契约。
- [`docs/01_ARCHITECTURE.md`](./docs/01_ARCHITECTURE.md)：当前架构说明。

## 安全边界

- 不输出买入/卖出建议。
- What Changed 和 Risk Lens 只给研究复查路径。
- `.env`、数据库、上传文件、日志、本地记忆、测试报告和 Playwright 产物默认不进入 Git。
