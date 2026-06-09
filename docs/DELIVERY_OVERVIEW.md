# FinSight 交付总览

**最后更新**: 2026-06-09  
**默认链路**: `frontend-vue -> FastAPI`  
**当前状态**: 代码层稳定可交付；生产发布仍取决于密钥与外部服务配置。

---

## 1. 快速结论

FinSight 已完成从金融 AI 演示系统到证据驱动研究工作台的核心升级。

| 维度 | 状态 | 说明 |
|---|---|---|
| 核心功能 | ✅ 完成 | Dashboard、Chat、Reports、Portfolio、Watchlist、Alerts、Today Workspace 均可用 |
| 研究闭环 | ✅ 完成 | Risk Lens、Notebook、Timeline、What Changed、Research Quality 已形成闭环 |
| E2E 稳定性 | ✅ 完成 | Phase 6 完成 48/48 E2E 全绿 |
| 发布硬化 | ✅ 完成 | Release gate、性能、文档、工作区审计已收口 |
| 生产预演 | ✅ 部分完成 | Docker smoke、API smoke、上传闭环已验证 |
| 最终上线 | ⚠️ 待环境配置 | `JWT_SECRET`、`API_AUTH_KEYS`、有效 LLM key 仍是生产前置 |

---

## 2. Phase 4-9 合并摘要

### Phase 4: 证据驱动研究体验

目标是让系统不仅能生成分析，还能解释风险、保存人工判断、追踪证据演化并校准研究质量。

| 子阶段 | 能力 | 状态 |
|---|---|---|
| 4.1 | Portfolio Risk Lens，多维持仓风险评估 | ✅ |
| 4.2 | Research Notebook，Markdown 笔记与图片上传 | ✅ |
| 4.3 | Evidence Timeline，统一事件时间线 | ✅ |
| 4.4 | What Changed，今日重要变化识别 | ✅ |
| 4.5 | Research Quality，研究库健康度校准 | ✅ |

关键验证：
- 后端 Phase 4 单元测试：29/29 通过。
- Phase 4 E2E：9/9 通过。
- TypeScript 与 build 通过。

权威明细：
- `docs/archive/phase-delivery/PHASE4_FINAL_SUMMARY.md`
- `docs/archive/phase-delivery/PHASE4_DELIVERY_SNAPSHOT.md`
- `VERIFICATION_CHECKLIST.md`

### Phase 5: 发布硬化与体验收口

目标是把功能完成状态推进到稳定可交付快照。

| 项 | 状态 |
|---|---|
| Release Gate 验证 | ✅ |
| 性能基准 | ✅ |
| 前端体验硬化 | ✅ |
| 文档与架构收口 | ✅ |
| 工作区审计 | ✅ |
| 最终交付报告 | ✅ |

权威明细：
- `docs/archive/phase-delivery/PHASE5_FINAL_DELIVERY_REPORT.md`
- `docs/archive/phase-delivery/PHASE5_RELEASE_GATE_REPORT.md`
- `docs/archive/phase-delivery/PHASE5_PERFORMANCE_REPORT.md`
- `docs/archive/phase-delivery/PHASE5_UX_HARDENING_NOTES.md`
- `docs/archive/phase-delivery/PHASE5_WORKTREE_AUDIT.md`

### Phase 6: E2E 稳定化

目标是清理历史遗留 E2E 失败并统一 mock 策略。

| 指标 | 结果 |
|---|---|
| 初始失败数 | 22 |
| 最终失败数 | 0 |
| 完整 E2E | 48/48 通过 |
| TypeScript 错误 | 0 |
| skip 数量 | 0 |

核心成果：
- 新增统一 E2E mock helper。
- 修复多 API 并发页面 mock 缺失问题。
- 把测试体系从局部可用提升为稳定回归基线。

权威明细：
- `docs/archive/phase-delivery/PHASE6_E2E_STABILIZATION_REPORT.md`
- `docs/archive/phase-delivery/PHASE6_E2E_FAILURE_AUDIT.md`

### Phase 7: 发布候选验证

目标是执行本地真实链路 smoke、API smoke、性能复测和发布候选评估。

| 项 | 结果 |
|---|---|
| E2E | 48/48 通过 |
| API smoke | 12/12 通过 |
| 性能 | P95 < 30ms |
| TypeScript | 0 错误 |
| Compose config | 默认/dev/smoke 三种模式通过 |
| 结论 | READY_WITH_NOTES |

权威明细：
- `docs/archive/phase-delivery/PHASE7_RELEASE_CANDIDATE_REPORT.md`
- `docs/archive/phase-delivery/PHASE7_API_SMOKE_REPORT.md`
- `docs/archive/phase-delivery/PHASE7_ENV_MATRIX.md`

### Phase 8: 生产预演与运维准备

目标是补齐 Docker smoke、运维手册、备份恢复、回滚和可观测性清单。

| 项 | 结果 |
|---|---|
| Docker smoke | 15/15 通过 |
| RAG init | hash fallback 通过，BGE-M3 待网络/模型环境验证 |
| 外部 API | LLM key 无效，代码路径正常 |
| 运维手册 | 备份与回滚手册完成 |
| 结论 | READY_WITH_BLOCKERS |

权威明细：
- `docs/archive/phase-delivery/PHASE8_READY_ASSESSMENT.md`
- `docs/archive/phase-delivery/PHASE8_DOCKER_SMOKE_REPORT.md`
- `docs/BACKUP_RESTORE_RUNBOOK.md`
- `docs/ROLLBACK_RUNBOOK.md`

### Phase 9: 密钥与最终上线确认

目标是验证生产密钥前置项。当前代码逻辑验证通过，但真实生产配置仍需补齐。

| 阻塞项 | 当前口径 |
|---|---|
| `JWT_SECRET` | 生产值仍需写入 `.env.server` |
| `API_AUTH_KEYS` | 生产值仍需写入 `.env.server` |
| LLM key | 当前记录显示旧 key 无效；需替换有效 key 并重跑最小 smoke |

最终结论以 `docs/RELEASE_READINESS.md` 为准。

---

## 3. 当前应优先阅读的文档

| 目的 | 文档 |
|---|---|
| 项目入口 | `README.md` / `readme_cn.md` |
| 架构理解 | `docs/01_ARCHITECTURE.md` |
| 交付总览 | `docs/DELIVERY_OVERVIEW.md` |
| 发布状态 | `docs/RELEASE_READINESS.md` |
| 生产运行 | `docs/11_PRODUCTION_RUNBOOK.md` |
| 备份恢复 | `docs/BACKUP_RESTORE_RUNBOOK.md` |
| 回滚 | `docs/ROLLBACK_RUNBOOK.md` |
| 完整验证清单 | `VERIFICATION_CHECKLIST.md` |

---

## 4. 文档治理原则

- 根目录 Phase 报告保留为审计证据，不作为日常入口。
- `docs/DELIVERY_OVERVIEW.md` 汇总功能交付状态。
- `docs/RELEASE_READINESS.md` 汇总发布与阻塞项状态。
- 新增阶段报告后必须登记到 `docs/DOCS_INDEX.md`。
- 不确定是否废弃的文档先归档或降级为附录，不直接删除。

