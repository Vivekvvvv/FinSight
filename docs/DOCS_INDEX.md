# FinSight 文档索引

**最后更新**: 2026-06-11
**用途**: 给维护者提供当前有效入口；历史报告保留为审计证据，不作为默认运行链路。

## 推荐阅读顺序

| 顺序 | 文档 | 用途 |
|---|---|---|
| 1 | `README.md` / `readme_cn.md` | 项目入口、启动方式、能力概览 |
| 2 | `docs/PROJECT_TIMELINE.md` | 证据化项目时间线，不伪造 commit 日期 |
| 3 | `docs/DELIVERY_OVERVIEW.md` | Phase 4-9 交付总览 |
| 4 | `docs/RELEASE_READINESS.md` | 发布状态、阻塞项和最小验证 |
| 5 | `docs/API_CONTRACT_CURRENT.md` | 当前 FastAPI 契约与 demo/live 差异 |
| 6 | `docs/01_ARCHITECTURE.md` | 当前 Vue + FastAPI 架构 |

## 当前维护入口

- `docs/01_ARCHITECTURE.md`: 当前系统架构与默认链路。
- `docs/AGENTS_GUIDE.md`: Agent 与工具链路说明。
- `docs/API_CONTRACT_CURRENT.md`: 当前核心 API 契约。
- `docs/DELIVERY_OVERVIEW.md`: Phase 4-9 合并交付说明。
- `docs/PRODUCT_BASELINE.md`: 产品完成度与边界。
- `docs/PRODUCT_FLOWS.md`: 核心用户流程。
- `docs/PROJECT_TIMELINE.md`: 阶段时间线与日期可信度。
- `docs/RELEASE_READINESS.md`: 发布状态与阻塞项。

## 运行与发布

- `docs/deploy.md`: 部署说明。
- `docs/11_PRODUCTION_RUNBOOK.md`: 生产运行手册。
- `docs/BACKUP_RESTORE_RUNBOOK.md`: 备份恢复手册。
- `docs/ROLLBACK_RUNBOOK.md`: 回滚手册。

## 维护记录

- `docs/maintenance/PROGRESS.md`: 历史会话进度摘要。
- `docs/maintenance/VERIFICATION_CHECKLIST.md`: 验证清单。
- `docs/maintenance/DOCUMENTATION_CLEANUP_REPORT.md`: 文档整理记录。
- `docs/maintenance/SECURITY_FIXES.md`: 安全修复矩阵。

## 历史归档

- `docs/archive/PHASE_DELIVERY_ARCHIVE.md`: Phase 4-9 交付报告总入口。
- `docs/archive/phase-delivery/`: Phase 4-9 原始交付证据。
- `docs/archive/legacy-notes/`: 更早期的 README、summary、testing 类历史草稿。

归档文档只用于追溯，不代表当前运行链路。当前主线始终是：

```text
frontend-vue -> FastAPI
```

## 不进入公开提交的内容

- `.env`、`.env.server`、真实密钥、数据库、日志、上传文件。
- Playwright 结果、pytest 临时目录、构建产物和本地缓存。
- 旧 React/Spring 运行代码、临时参考目录和本地 agent 会话记忆。

## 文档治理规则

- 当前有效结论优先更新 `README.md`、`readme_cn.md`、`docs/DELIVERY_OVERVIEW.md` 或 `docs/RELEASE_READINESS.md`。
- API 或 demo/live 行为变化必须更新 `docs/API_CONTRACT_CURRENT.md`。
- 新阶段或重要交付必须更新 `docs/PROJECT_TIMELINE.md` 和对应归档入口。
- 后补文档必须说明证据来源，不用 Git 日期伪装原始开发日期。
