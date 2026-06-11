# FinSight 项目时间线

**最后更新**：2026-06-09  
**性质**：公开/本地重建历史的证据化说明，不等同于原始 Git 提交历史。

## 说明

FinSight 早期主要在本地工作区和 AI Agent 会话中迭代，原始提交历史没有完整保留。为了避免把个人邮箱、运行记忆、会话摘要、日志、数据库或疑似密钥写进公开历史，本项目采用干净新历史。

本时间线不伪造 commit 日期，只记录阶段顺序、主要成果、证据来源和可信度。

可信度定义：

| 可信度 | 含义 |
|---|---|
| 高 | 有明确日期、测试结果、阶段报告或交付文档佐证 |
| 中 | 有会话汇总或后补文档佐证，但可能经过复盘整理 |
| 低 | 只能确认阶段顺序，缺少可靠日期证据 |

## 阶段时间线

| 阶段 | 日期/范围 | 主要成果 | 证据来源 | 可信度 |
|---|---|---|---|---|
| 早期多 Agent / LangGraph 基线 | 2026-05 上旬 | 多 Agent 金融研究、RAG、报告生成、基础测试收口 | `docs/maintenance/PROGRESS.md`、早期架构文档 | 中 |
| Spring + Vue 迁移探索 | 2026-05 下旬 | 探索 Spring shadow API、Vue 骨架、迁移验收和切流脚手架 | 迁移文档、历史脚本、会话记录 | 中 |
| Python + Vue 默认链路稳定化 | 2026-05-31 ~ 2026-06-01 | 默认链路收敛为 `frontend-vue -> backend/FastAPI`，旧 React/Spring 退出主线 | `docs/PRODUCT_BASELINE.md`、切流校验脚本 | 高 |
| Phase 0 稳定收口 | 2026-06 上旬 | 路由校验、后端 smoke、前端 typecheck、13 条 E2E 全绿 | 会话汇总、验证清单 | 中 |
| Phase 2 报告资产化 | 2026-06 上旬 | Reports Library、标签、备注、版本对比、MD 导出、21 条 E2E | 会话汇总、E2E 记录 | 中 |
| Phase 3 Today Workspace | 2026-06 上旬 | `/api/today`、Next Actions、欢迎页工作台、28 条 E2E | `docs/maintenance/VERIFICATION_CHECKLIST.md`、会话汇总 | 中 |
| Phase 4 证据驱动研究体验 | 2026-06-08 | Risk Lens、Research Notebook、Timeline、What Changed、Research Quality | `docs/archive/phase-delivery/PHASE4_FINAL_SUMMARY.md` | 高 |
| Phase 5 发布硬化 | 2026-06-08 | Release Gate、性能基准、体验硬化、文档收口、工作区审计 | `docs/archive/phase-delivery/PHASE5_FINAL_DELIVERY_REPORT.md` | 高 |
| Phase 6 E2E 稳定化 | 2026-06-08 | 完整 E2E 从 22 个失败收敛到 48/48 全绿 | `docs/archive/phase-delivery/PHASE6_E2E_STABILIZATION_REPORT.md` | 高 |
| Phase 7 发布候选 | 2026-06-08 | API smoke、性能复测、Compose 验证、RC 报告 | `docs/archive/phase-delivery/PHASE7_RELEASE_CANDIDATE_REPORT.md` | 高 |
| Phase 8 生产预演 | 2026-06-09 | Docker smoke、环境审计、外部 API smoke、运维/备份/回滚手册 | `docs/archive/phase-delivery/PHASE8_READY_ASSESSMENT.md` | 高 |
| Phase 9 密钥与最终确认 | 2026-06-09 | 安全配置检查、最小发布 smoke、最终阻塞项复核 | `docs/archive/phase-delivery/PHASE9_READY_FINAL_ASSESSMENT.md`、`docs/RELEASE_READINESS.md` | 高 |
| 干净本地仓库重建 | 2026-06-09 | 删除旧 `.git` 历史、清理旧迁移残留、从今天开始本地 commit | 本文件、README、最终 Git 历史 | 高 |

## 维护规则

- 新增阶段时同步更新本文件和 `docs/DOCS_INDEX.md`。
- 后补文档必须标注证据来源，不能把复盘整理伪装成原始提交记录。
- Git 提交日期只代表整理入库时间，不作为唯一事实来源。
