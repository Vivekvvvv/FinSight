# FinSight 文档索引

**最后更新**：2026-06-09  
**用途**：给新仓库保留当前权威文档和必要交付证据，避免旧 React/Spring 草稿继续误导维护。

## 推荐阅读顺序

| 顺序 | 文档 | 用途 |
|---|---|---|
| 1 | `README.md` / `readme_cn.md` | 项目入口、当前能力、启动方式 |
| 2 | `docs/PROJECT_TIMELINE.md` | 证据化阶段时间线，说明为什么不伪造历史 commit 日期 |
| 3 | `docs/DELIVERY_OVERVIEW.md` | Phase 4-9 交付总览 |
| 4 | `docs/RELEASE_READINESS.md` | 发布就绪状态、阻塞项和最小验证 |
| 5 | `docs/01_ARCHITECTURE.md` | 当前 Vue + FastAPI 架构 |
| 6 | `docs/PRODUCT_FLOWS.md` | 核心产品流程 |
| 7 | `docs/11_PRODUCTION_RUNBOOK.md` | 生产运行与排障 |
| 8 | `docs/BACKUP_RESTORE_RUNBOOK.md` | 备份恢复 |
| 9 | `docs/ROLLBACK_RUNBOOK.md` | 回滚 |

## 当前权威文档

- `README.md`：英文入口。
- `readme_cn.md`：中文入口。
- `docs/01_ARCHITECTURE.md`：系统架构与默认链路。
- `docs/AGENTS_GUIDE.md`：Agent 与工具链路说明。
- `docs/API_CONTRACT_BASELINE.md`：FastAPI 契约快照。
- `docs/DELIVERY_OVERVIEW.md`：Phase 4-9 合并交付说明。
- `docs/PRODUCT_BASELINE.md`：产品完成度与边界。
- `docs/PRODUCT_FLOWS.md`：用户流程。
- `docs/PROJECT_TIMELINE.md`：阶段时间线和日期可信度。
- `docs/RELEASE_READINESS.md`：发布状态与阻塞项。
- `docs/deploy.md`：部署说明。
- `docs/11_PRODUCTION_RUNBOOK.md`：生产运行手册。
- `docs/BACKUP_RESTORE_RUNBOOK.md`：备份恢复手册。
- `docs/ROLLBACK_RUNBOOK.md`：回滚手册。

## 阶段交付证据

Phase 4-9 的详细报告保留在 `docs/archive/phase-delivery/`。这些文件只作为审计证据，不作为日常维护入口。

## 明确不进入新历史的内容

- 旧 React 前端源码和旧 Spring 迁移脚手架。
- 本地运行数据：`.env`、数据库、日志、上传文件、Playwright 产物、pytest 临时目录。
- 本地 agent 指令、会话记忆、长周期草稿和旧功能日志。
- 只适合本地复盘的历史草稿目录：`docs/feature_logs/`、`docs/Thinking/`、`docs/plans/`、`docs/design/`、`docs/prototype/`。

## 文档治理规则

- 新增当前有效结论，优先更新 `README.md`、`readme_cn.md`、`docs/DELIVERY_OVERVIEW.md` 或 `docs/RELEASE_READINESS.md`。
- 新增阶段时同步更新 `docs/PROJECT_TIMELINE.md`。
- 后补文档必须说明证据来源，不用 Git 日期伪装原始开发日期。
- 旧系统只能作为历史说明出现，不能被描述为当前运行链路。
