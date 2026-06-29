# FinSight 产品完成度基线（Product Baseline）

> 基于 2026-05-13 真实代码与测试结果。本文件按模块评估完成度、缺口、风险、建议优先级，用于后续产品升级排期。后续阶段完成后请追加日期化的"复评"段落，不要覆盖原始基线。

**当前总体完成度估算**：**~90%**（可演示 / 小规模内测标准）/ **~80%**（生产候选标准）。

**最近一次代码核对**：2026-06-29。当前主线已收敛为 `frontend-vue -> FastAPI`，主导航为 7 个入口：`/welcome`、`/dossier/:symbol`、`/stocks`、`/portfolio`、`/reports`、`/notes`、`/chat`。最近一次完整门禁记录见 `docs/maintenance/PROGRESS.md`；发布状态仍以 `docs/RELEASE_READINESS.md` 的生产密钥和外部服务验证为准。

---

## 完成度评级标准

- **✅ 完成**：核心能力已落地，测试覆盖，可对真实用户开放。
- **🟡 部分完成**：主链路通畅但缺收口（如无历史/对比/管理界面）；可用但有 UX 摩擦。
- **🟠 占位**：代码骨架存在但未投产（如 Phase Labs 实验）。
- **🔴 缺失**：完全没做。

---

## 模块基线

### 1. 标的研究 / Dossier

| 维度 | 状态 | 说明 |
|---|---|---|
| 完成度 | ✅ 90% | 旧 Dashboard 能力已并入 `/dossier/:symbol`，覆盖报价、K 线、财务、新闻、AI 洞察、时间线、报告与笔记 |
| 数据 | ✅ | 16 个 TTL 缓存分类；11 源价格瀑布；US/CN/HK 三套路由 |
| AI Insight | ✅ | 5 个 Scorer，含 LLM 单次调用 + 确定性规则降级 |
| Smart Charts | ✅ | `<chart>` + `<chart_ref>` 双模；ECharts 6 |
| 缺口 | 🟡 | 标的页仍承载信息较多，后续可继续压缩首屏密度与增强锚点 |
| 风险 | P3 | Dashboard API 仍作为后端兼容层存在，文档和命名需持续避免把它误认为主页面 |
| 建议优先级 | P2 | 继续补 Dossier 内部区域锚点和移动端体验 |

### 2. Chat / Research

| 维度 | 状态 | 说明 |
|---|---|---|
| 完成度 | ✅ 90% | LangGraph 18-node pipeline 完整链路、Persona Mode v1.2、ThinkingBubble 三层展示 |
| 多 Agent | ✅ | 7 个 Research Agent（Price / News / Fundamental / Technical / Macro / Risk / DeepSearch） |
| 历史会话 | ✅ | ChatHistorySidebar（本会话补齐）+ localStorage 50 会话 |
| 导出 | ✅ | 顶部"导出 PDF"按钮（本会话接通后端） |
| RAG | ✅ | Hybrid bge-m3 + bge-reranker-v2-m3 |
| Conflict Detection | ✅ | 8 对 Agent 对比维度 |
| 缺口 | 🟡 | 对话搜索 / 导出 markdown 缺失；本地 memory 已有，但跨设备/多用户长期记忆仍依赖后续配置 |
| 风险 | P3 | 会话内若 SSE 连接中断，恢复后无 resume 提示 |
| 建议优先级 | P3 | 阶段 3 报告资产化时一并处理对话历史 |

### 3. Portfolio

| 维度 | 状态 | 说明 |
|---|---|---|
| 完成度 | 🟡 75% | `/portfolio` 已是核心入口，包含持仓摘要、持仓维护、风险镜头、组合工具和旧 backtest/optimize 入口收口 |
| CRUD | 🟡 | 支持持仓增改和基础校验；仍缺交易流水、lot 级成本与多币种 |
| Summary | 🟡 | 总市值、成本、盈亏、主要仓位已有；跨市场估值仍依赖数据源质量 |
| Rebalance | ✅ | LLM 增强 + Agent 支撑 + SSE 流式，旧 `/portfolio/optimize` redirect 到组合工具区 |
| 缺口 | 🟡 | 多币种、交易流水、CSV 导出和更严格的数据一致性仍未完成 |
| 风险 | P1 | 数据正确性与显示一致性，特别是多币种与跨市场标的 |
| 建议优先级 | **P1** | **阶段 1 留存闭环的核心** |

### 4. Watchlist

| 维度 | 状态 | 说明 |
|---|---|---|
| 完成度 | 🟡 70% | 独立主入口已下沉，自选高频能力并入 `/stocks` 与 `/welcome` 上下文 |
| 数据模型 | 🟡 | 已支持基础关注理由、优先级、研究状态；分组/标签能力仍有限 |
| UI | 🟡 | 股票发现页和今日工作台消费自选数据，不再作为主导航入口 |
| 缺口 | 🟠 | 批量导入、排序、分组管理仍需增强 |
| 风险 | P2 | 需要继续保证 `/watchlist -> /stocks?tab=watchlist` 的跳转和目标区可见性 |
| 建议优先级 | **P1** | **阶段 1 任务 T10-T12** |

### 5. Alerts

| 维度 | 状态 | 说明 |
|---|---|---|
| 完成度 | 🟡 70% | 3 个调度器（PriceChange / News / Risk），APScheduler + SMTP |
| 创建路径 | ✅ | SubscribeModal + 对话内自然语言抽取（alert_extractor 节点） |
| 类型 | ✅ | `price_change` / `price_target` / `news` / `risk` |
| 邮件可达性 | ✅ | 3 次永久失败自动 disable |
| 缺口 | 🟠 | 独立入口已下沉到 `/welcome`，仍缺完整历史告警列表、in-app 通知和 webhook |
| 风险 | P2 | 用户不易看到当前已设的所有提醒 |
| 建议优先级 | **P1** | **阶段 0 IA 重构 + 阶段 4 gate** |

### 6. Reports

| 维度 | 状态 | 说明 |
|---|---|---|
| 完成度 | 🟡 80% | `/reports` 已是核心入口，`report_index` SQLite + replay endpoint + 生成报告/财报分析入口已接入 |
| 生成 | ✅ | 完整 LangGraph 流程 |
| 持久化 | ✅ | 报告元数据 + citations 落地 |
| PDF 导出 | ✅ | `services/pdf_export.py` reportlab + 字体管理 |
| Library 列表 | ✅ | 报告库已独立为核心页面 |
| 版本对比 / 收藏 / 备注 / 旧报告刷新 | 🟡 | 已有部分资产化体验，深度版本治理仍需加强 |
| 缺口 | 🟡 | 报告刷新策略、版本对比和引用质量解释仍可继续深化 |
| 风险 | P2 | 用户不会回来查历史 |
| 建议优先级 | **P1** | **阶段 3 报告资产化 (T27-T32)** |

### 7. RAG

| 维度 | 状态 | 说明 |
|---|---|---|
| 完成度 | ✅ 90% | Hybrid Search (RRF + scope boost) + Cross-Encoder Rerank |
| 模型 | ✅ | bge-m3 (1024 dim) + bge-reranker-v2-m3 |
| 存储 | ✅ | InMemory + PostgreSQL/pgvector + tsvector 中文全文 |
| 可观测 | ✅ | `rag_query_runs/events/source_docs/chunks/retrieval_hits/rerank_hits/fallback_events` 6 张表；独立 RagInspector 入口已下沉到数据源/系统状态抽屉 |
| Quality Eval | ✅ | RAG Quality V2 三层 PASS（KC/KCR/CSR/UCR/CR/NCR 六指标） |
| 缺口 | 🟡 | 自动化 reranker 选模型 / chunk size A-B 测试缺工具 |
| 风险 | P3 | 检索质量优化是后续迭代领域 |
| 建议优先级 | P3 | 已超出 MVP 范围 |

### 8. Auth

| 维度 | 状态 | 说明 |
|---|---|---|
| 完成度 | 🟡 70% | 3 套并行：Supabase Magic Link / API Key Principal / DEV_MODE 匿名 |
| 守卫 | ✅ | EntryGuard / AuthenticatedGuard 双层 |
| 身份范围 | ✅ | user / portfolio / subscription 都按 Principal scope |
| 缺口 | 🟠 | 无注册流程文案；无密码登录；dev auth token 通过 env 注入，权限边界靠 frontend 自觉 |
| 风险 | P1 | 商业化前需补 free / pro / team / admin 权限模型 |
| 建议优先级 | **P1** | **阶段 4 商业化基础 (T33-T34)** |

### 9. Billing / Permission

| 维度 | 状态 | 说明 |
|---|---|---|
| 完成度 | 🟠 占位 | 后端保留 entitlements/API 轮廓；前端套餐页、PlanBadge、UpgradeModal 空壳已移除，当前 7 入口不提供商业化体验 |
| 计划 | 暂缓 | 当前项目定位是个人研究工作台，不以商业化计费作为近期主线 |
| 风险 | P2 | 若未来重新商业化，需要先恢复产品策略、权限文案和真实支付设计 |
| 建议优先级 | P3 | 暂不作为当前体验修复重点 |

### 10. Deploy

| 维度 | 状态 | 说明 |
|---|---|---|
| 完成度 | 🟡 75% | docker-compose (prod + dev)；SQLite 自动建表；pgvector 可选；SMTP 可选 |
| 安全默认 | ✅ | 仅 frontend `80:80` 暴露；后端 / Postgres 只在内网 |
| 环境变量 | 🟡 | 3 类（dev / docker / prod）部分重复，缺统一对照表 |
| CI/CD | ✅ | `.github/workflows/ci.yml` 覆盖 frontend-vue lint/build/e2e、backend pytest、retrieval gate、compose smoke |
| 监控 | ✅ | Langfuse / LangSmith / Prometheus metrics 三套 |
| 缺口 | 🟡 | 本地 compose smoke、生产域名 smoke、真实 secrets/JWT/Supabase 验证仍需环境侧闭环 |
| 风险 | P1 | 当前工作区变更多，发布候选需要先固化干净快照 |
| 建议优先级 | P2 | 阶段 5 发布硬化 (T39-T40) |

### 11. Testing

| 维度 | 状态 | 说明 |
|---|---|---|
| 完成度 | ✅ 88% | 后端核心测试量级已超过 1000，Vue lint/typecheck/build 与 mock E2E 已接入门禁 |
| 单元 | ✅ | 后端覆盖 agents / orchestration / graph / rag / services / api |
| 集成 | ✅ | `tests/regression/` mock_tools 注入；`tests/rag_qualityV2/` 三层评估 |
| E2E | 🟡 | frontend-vue mock E2E 已覆盖 7 个核心入口、旧 URL redirect、状态抽屉和关键空状态；真实后端链路 smoke 仍需加强 |
| 性能 / 压测 | 🔴 | 无 |
| 缺口 | 🟡 | e2e 自动化覆盖率；缺 frontend dead-code 系统扫描（需 `knip`） |
| 风险 | P2 | UI 功能变更后只能靠手动 smoke |
| 建议优先级 | P2 | 阶段 5 release gate 时一起做 |

---

## 横向通用维度

| 维度 | 状态 | 说明 |
|---|---|---|
| Trust / Evidence | 🟡 | 后端 evidence_pool / citations / conflict detection 已落地；前端缺 EvidencePanel 组件统一展示 → **阶段 2 任务 T19-T26** |
| Disclaimer / 免责声明 | 🟡 | 散落在 ReportView 等少数位置；缺统一 `<Disclaimer>` 组件与全场景覆盖 |
| Data Freshness | 🟠 | 后端缓存有 TTL；前端未在 UI 上系统展示数据时间 → **阶段 2 任务 T23** |
| Persona Mode | ✅ | v1.2 完整：4 个内置 Persona + Picker + CompareModal |
| Hallucination 防御 | ✅ | 多层正则 + evidence cross-validation + 时间锚定 |
| Observability | ✅ | Trace 三视图 + raw SSE 控制台 + Langfuse |

---

## 已识别 P0 / P1 缺口（按修复成本排序）

| 优先级 | 项 | 估算 | 阶段 |
|---|---|---|---|
| **P0** | Feature Gate + Usage Limit + Pricing 页面（商业化打通） | 中 | 阶段 4 (T35-T37) |
| **P0** | Watchlist 2.0 + Portfolio 2.0 + Daily Brief 历史（留存闭环） | 中 | 阶段 1 (T9-T18) |
| **P0** | IA 重构 + WelcomePage 工作台化 + 空状态统一 | 小 | 阶段 0 (T2-T4) |
| **P1** | EvidencePanel + 数据新鲜度 + 报告分层 + ConflictPanel + 引用质量评分 | 中 | 阶段 2 (T19-T26) |
| **P1** | Report Library + 版本对比 + 收藏 + 旧报告刷新 | 中 | 阶段 3 (T27-T32) |
| **P1** | Auth Gap Report + 权限模型文档 | 小 | 阶段 4 (T33-T34) |
| **P1** | docs/STRIPE_INTEGRATION_PLAN.md | 小 | 阶段 4 (T38) |
| **P2** | Release Gate 脚本 + Runbook 更新 + Acceptance 报告 | 小 | 阶段 5 (T39-T40) |
| **P2** | env 变量文档对齐 / frontend README 重写 / PRODUCT_FLOWS 维护 | 小 | 阶段 0（本批已完成） |

---

## 风险清单（投产前需关闭）

| 风险 | 影响 | 缓解策略 |
|---|---|---|
| 商业化模型未打通 | 无法收费 | 阶段 4 |
| Reports 不可沉淀 | 用户留存差 | 阶段 3 |
| 数据时效性 UI 不显示 | 可能传递过期信息为"事实" | 阶段 2 任务 T23 |
| Alerts 无独立页面 / 历史 | 用户难以管理 | 阶段 0 IA 重构 |
| Watchlist 无分组 / 标签 | 自选股管理粗 | 阶段 1 任务 T10-T12 |
| Auth 权限模型不存在 | 无法做 plan 区分 | 阶段 4 任务 T33-T34 |
| Vue E2E 真实链路覆盖薄 | 重构容易 regression | 先补 mock 页稳定性，再补最小真实健康链路 smoke |
| `tmp/pytest-basetemp/` 被锁定残留 | 本地 dev 干扰 | 重启 PowerShell 后清理 |

---

## 历史复评记录

- **2026-06-29 复评 — 7 入口信息架构核对**：当前按可演示 / 小规模内测标准约 **90%**，按生产候选标准约 **80%**。真实前端入口已收敛为 7 个核心页面：今日工作台、标的研究、股票发现、组合管理、报告库、研究笔记、AI 助手；旧 Dashboard/Workbench/Watchlist/Alerts/Data Sources/System Health 等入口通过 redirect 或上下文抽屉下沉。当前主要风险从“功能缺失”转为“文档滞后、生产密钥/外部服务未验证、后端 main.py 装配偏重”。本次同步移除了未接入主线的前端商业化空壳。
- **2026-06-01 复评 — Python + Vue 生产候选收口**：当前按可演示 / 小规模内测标准约 **90%**,按生产候选标准约 **80%**。旧 React `frontend/` 与 Spring Boot `backend-spring/` 已归档删除，默认链路为 `frontend-vue -> backend/FastAPI`；`scripts/check_cutover_map.py` 已改为默认链路静态校验；`docker-compose.yml` 默认只暴露 `frontend:80`，后端与 Postgres 仅 Compose 内网访问。当前轻量验证：`backend.import-smoke` 通过，Vue `build` 通过，`python scripts/check_cutover_map.py` 通过。剩余主要缺口：工作区仍有大量未固化变更，真实 Supabase/JWT、生产数据库/API、Docker compose 本地 smoke、生产域名级 smoke、Vue Playwright 真实链路 E2E 仍需上线前闭环。
- **2026-05-19 复评 #2 — Plan 门控真实生效 + 商业化 UX 闭环**：当前按可演示/小规模内测标准约 **94%**,按完整商业交付标准约 **89%**。本日完成的关键升级:
  - **Plan 门控真实生效**: `entitlements.enforce_feature` / `enforce_quota` 已注入 `/chat/supervisor` (`investment_report` → `deep_research`)、`/chat/supervisor/stream`、`/api/export/pdf` (`export_pdf`),前端 axios interceptor 统一识别 403/429 `plan_*` 错误并 dispatch `finsight:plan-gate` 事件。
  - **Usage 计数后端**: `build_usage_view(user_id, email)` 综合 report_index/订阅/portfolio 计算 5 个配额的 used/limit/remaining/percent;`GET /api/me/entitlements` 现含 `usage` 字段,新增 `GET /api/me/usage` 与 `GET /api/plans`。
  - **商业化 UX 三件套（历史状态）**: 当时曾有 `PlanBadge`、`/settings/plan` 和全局 `<UpgradeModal/>`；2026-06-29 已按当前 7 入口主线移除未接入的前端空壳。
  - **后端基线**: backend/tests `1007 passed / 18 skipped` (新增 16 测试)。前端 4 件套全绿。Playwright `standalone-pages.spec.ts` **7/7 passed in 22s**,release_gate `-WithE2E` 模式稳定可用。
  - 剩余主要缺口: Stripe 真实支付(占位用 mailto:);报告版本对比 / 旧报告刷新入口;evidence/citation 在前端的统一展示组件(本轮即将做);Portfolio 多币种与数据时效徽章。
- **2026-05-19 复评 — Release/留存闭环**:当前按可演示/小规模内测标准约 **91%**,按完整商业交付标准约 **84%**。Feature Gate 已具备 usage/limit、套餐页与升级引导;Reports Library 已具备列表、收藏、备注、引用数量;Watchlist/Portfolio 已有独立管理页,其中 Portfolio 新增 CSV 导入与成本价非负校验;Release Gate `-WithE2E` 已能稳定串起后端核心测试、前端四件套与 standalone pages smoke(8/8 passed)。剩余主要缺口转为 Stripe 真实支付、报告版本对比/旧报告刷新、Portfolio 多币种与更严谨交易流水、Alerts in-app 通知与触发历史深化。
- **2026-05-13** 初版基线(本文件创建)。基于退役 deprecated 路径后的 baseline:后端 1036 passed / 0 failures,前端 lint 0/0、build 2834 modules,新增对话历史侧栏 + 导出 PDF。

> 后续每完成一个阶段，请在此追加 "## YYYY-MM-DD 复评 — 阶段 X" 段落，对照本基线更新模块状态与完成度。
