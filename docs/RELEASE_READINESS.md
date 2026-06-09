# FinSight 发布就绪状态

**最后更新**: 2026-06-09  
**当前判定**: `READY_WITH_BLOCKERS`  
**原因**: 代码、容器、E2E、API smoke 已通过；最终生产发布仍依赖真实密钥和外部服务配置。

---

## 1. 一句话结论

FinSight 代码层已经达到稳定可部署状态；发布前必须补齐 `JWT_SECRET`、`API_AUTH_KEYS` 和有效 LLM API key，并执行最小发布确认。

---

## 2. 验证矩阵

| 验证项 | 最新结果 | 证据文档 |
|---|---|---|
| 完整 E2E | ✅ 48/48 | `docs/archive/phase-delivery/PHASE6_E2E_STABILIZATION_REPORT.md` |
| API smoke | ✅ 12/12 | `docs/archive/phase-delivery/PHASE7_API_SMOKE_REPORT.md` |
| 性能复测 | ✅ P95 < 30ms | `docs/archive/phase-delivery/PHASE7_PERFORMANCE_RECHECK.md` |
| Compose config | ✅ 默认/dev/smoke 通过 | `docs/archive/phase-delivery/PHASE7_COMPOSE_VALIDATION.md` |
| Docker smoke | ✅ 15/15 | `docs/archive/phase-delivery/PHASE8_DOCKER_SMOKE_REPORT.md` |
| Notes 上传闭环 | ✅ 通过 | `docs/archive/phase-delivery/PHASE7_UPLOAD_SMOKE_REPORT.md` / `docs/archive/phase-delivery/PHASE8_DOCKER_SMOKE_REPORT.md` |
| RAG smoke | ✅ hash fallback 通过 | `docs/archive/phase-delivery/PHASE8_RAG_INIT_REPORT.md` |
| Auth 代码逻辑 | ✅ 测试值通过 | `docs/archive/phase-delivery/PHASE9_AUTH_FINAL_CHECK.md` |
| 外部 LLM | ⚠️ 旧 key 403；需有效 key | `docs/archive/phase-delivery/PHASE9_EXTERNAL_API_FINAL_CHECK.md` |
| 生产密钥 | ❌ 待补齐 | `docs/archive/phase-delivery/PHASE9_SECRET_READINESS_REPORT.md` |

---

## 3. 发布阻塞项

| 编号 | 阻塞项 | 当前状态 | 解决方式 |
|---|---|---|---|
| B1 | `JWT_SECRET` | 生产值待配置 | 生成 ≥64 字节随机值并写入 `.env.server` 或部署平台 secret |
| B2 | `API_AUTH_KEYS` | 生产值待配置 | 生成至少 1 个高熵 token 并写入 secret |
| B3 | LLM API key | 当前旧 key 记录为无效 | 替换为有效 provider key，并执行最小 LLM smoke |

> 本文采用保守口径：只要密钥报告或外部 API 报告仍记录缺失/无效，最终状态保持 `READY_WITH_BLOCKERS`。如果环境已补齐，请重跑最小确认并更新本文与 `docs/archive/phase-delivery/PHASE9_READY_FINAL_ASSESSMENT.md`。

---

## 4. 升级为 READY 的最小确认

配置 B1/B2/B3 后执行：

```powershell
docker compose --env-file .env.server config --quiet
python scripts/phase9_minimal_release_smoke.py
```

如果脚本不可用，至少手动验证：

```powershell
curl.exe http://localhost:18080/health
curl.exe http://localhost:18080/api/me
```

并执行：

- 用有效 API key 调用 `/api/me`。
- 用有效 LLM key 发起最小 Chat smoke。
- 调用 `/api/today`。
- 调用 `/api/research-quality`。
- 调用 `/api/what-changed`。
- 创建 note，上传小图，访问图片 URL。

全部通过后，发布状态可升级为 `READY`。

---

## 5. 非阻塞注意事项

| 项 | 说明 |
|---|---|
| 行情 API key | 未配置时系统降级，不阻塞核心研究工作台 |
| SMTP | 未配置时邮件提醒不可用，不阻塞核心功能 |
| BGE-M3 | 生产语义 RAG 需模型下载；可先用 hash fallback 验证链路 |
| HTTPS/TLS | 需在真实域名上配置，不属于本地代码验证范围 |
| 外部告警 | 可观测性清单已给出，生产部署时补齐 |

---

## 6. 运维入口

| 场景 | 文档 |
|---|---|
| 生产运行 | `docs/11_PRODUCTION_RUNBOOK.md` |
| 部署指南 | `docs/deploy.md` |
| 备份恢复 | `docs/BACKUP_RESTORE_RUNBOOK.md` |
| 回滚 | `docs/ROLLBACK_RUNBOOK.md` |
| 可观测性 | `docs/archive/phase-delivery/PHASE8_OBSERVABILITY_CHECKLIST.md` |
| 环境变量 | `docs/archive/phase-delivery/PHASE7_ENV_MATRIX.md` |

---

## 7. 文档冲突处理规则

若阶段报告之间出现 `READY` 与 `READY_WITH_BLOCKERS` 冲突：

1. 以最新密钥检查和外部 API smoke 为准。
2. 只要 `JWT_SECRET`、`API_AUTH_KEYS` 或 LLM key 未被真实验证，状态保持 `READY_WITH_BLOCKERS`。
3. 不因“代码逻辑通过”直接升级为 `READY`。

