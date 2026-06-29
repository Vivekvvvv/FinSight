# FinSight 文档索引

**最后更新**：2026-06-29
**当前主线**：`frontend-vue -> FastAPI`
**产品边界**：只做投资研究分析与证据复查，不提供交易建议。

## 推荐阅读顺序

| 顺序 | 文档 | 用途 |
|---|---|---|
| 1 | `README.md` / `readme_cn.md` | 项目入口、启动方式、能力概览 |
| 2 | `docs/API_CONTRACT_CURRENT.md` | 当前 API 契约、Demo/Live/Fallback 行为 |
| 3 | `docs/PRODUCT_BASELINE.md` | 产品定位、完成度和边界 |
| 4 | `docs/PRODUCT_FLOWS.md` | 核心研究闭环流程 |
| 5 | `docs/RELEASE_READINESS.md` | 发布状态、阻塞项和最小确认 |
| 6 | `docs/PROJECT_TIMELINE.md` | 证据化项目时间线，不伪造 commit 日期 |

## 当前维护入口

- `docs/01_ARCHITECTURE.md`：当前 Vue + FastAPI 架构，含 7 个核心入口与旧 URL redirect 策略。
- `docs/API_CONTRACT_CURRENT.md`：当前核心 API、字段和数据源 evidence。
- `docs/DELIVERY_OVERVIEW.md`：Phase 4-9 交付总览。
- `docs/PRODUCT_BASELINE.md`：产品完成度与范围边界。
- `docs/PRODUCT_FLOWS.md`：当前 7 个核心页面的研究闭环与旧入口收口规则。
- `docs/RELEASE_READINESS.md`：发布就绪状态与阻塞项。
- `docs/AGENTS_GUIDE.md`：Agent 使用和协作说明。
- `docs/DASHBOARD_DEVELOPMENT_GUIDE.md` / `docs/DASHBOARD_P0_DATA_TRACE.md`：历史文件名保留，当前内容描述 `/dossier/:symbol` 使用的 dashboard 兼容数据层。

## 运行与发布

- `docs/deploy.md`：部署说明。
- `docs/11_PRODUCTION_RUNBOOK.md`：生产运行手册。
- `docs/BACKUP_RESTORE_RUNBOOK.md`：备份恢复手册。
- `docs/ROLLBACK_RUNBOOK.md`：回滚手册。
- `scripts/local_release_gate.py`：本地发布门禁脚本。

## 归档入口

- `docs/archive/PHASE_DELIVERY_ARCHIVE.md`：Phase 4-9 原始交付报告总入口。
- `docs/archive/phase-delivery/`：阶段报告原文，仅作证据追溯。
- `docs/archive/legacy-notes/`：更早期草稿和历史参考，不代表当前运行链路。

## 不进入公开提交的内容

- `.env`、`.env.server`、真实密钥、`user_config.json`。
- 数据库、上传文件、运行日志、本地记忆、Playwright 报告、pytest 临时目录。
- 旧 React/Spring 运行代码、临时参考目录、agent 会话记忆。

## 文档治理规则

- API 或 Demo/Live 行为变化时，必须更新 `docs/API_CONTRACT_CURRENT.md`。
- 发布状态变化时，必须更新 `docs/RELEASE_READINESS.md`。
- 新阶段或重要交付完成时，必须更新 `docs/PROJECT_TIMELINE.md` 或归档入口。
- 后补文档必须说明证据来源，不用 Git 日期伪装原始开发日期。
