# FinSight Security Fixes Matrix

> 当前工作区不是 Git 仓库，本轮未创建 commit。`commit` 列使用建议提交标题，便于后续拆分提交。

| 条目 | 建议提交 | 核心文件 | 验收 |
|---|---|---|---|
| P0-1 默认凭据/端点移除 | `fix(security): fail fast on missing production secrets` | `backend/api/main.py`, `docker-compose.yml`, `.env.example`, `.env.server.example` | `docker compose config` 在缺少必填 env 时 fail-fast；旧真实形态默认值 grep 已清理 |
| P0-2 生产默认鉴权/限流 | `fix(security): enable auth and rate limits by default` | `backend/api/main.py`, `backend/security/auth.py` | 非 `DEV_MODE` 默认要求 API key；`DEV_MODE=1` 启动日志包含 `DEV_MODE ON — auth bypassed` |
| P0-3 收紧端口暴露 | `chore(infra): restrict default compose port exposure` | `docker-compose.yml`, `docker-compose.dev.yml`, `docs/deploy.md` | 默认 compose 仅暴露 frontend `80`; Postgres/Backend 仅 `expose`; 本地开发用 `docker-compose.dev.yml` |
| P0-4 `/health` 脱敏 | `fix(security): make public health endpoint non-sensitive` | `backend/api/system_router.py`, `backend/tests/test_health_and_validation.py` | `/health` 无 `components`、`recent_runs`、`query_text`; 详细健康迁到 admin/internal |
| P0-5 RAG 诊断脱敏 | `fix(security): redact rag diagnostics by role` | `backend/api/system_router.py`, `backend/rag/observability_store.py`, `backend/tests/test_rag_observability_system_router.py` | 普通用户无 `query_text/content_raw/chunk_text`; admin `include=raw` 才返回 |
| P0-6 principal 身份推导 | `fix(security): derive user scope from authenticated principal` | `backend/security/auth.py`, `backend/api/user_router.py`, `backend/api/portfolio_router.py`, `backend/api/subscription_router.py`, `backend/tests/test_auth_principal.py` | 伪造 `user_id/session_id/email` 返回 403 |
| P0-7 禁止订阅枚举 | `fix(security): prevent subscription enumeration` | `backend/api/subscription_router.py`, `backend/services/subscription_service.py`, `backend/tests/test_subscription_security.py` | 普通路径只返回当前 principal 邮箱；全量列表仅 admin-only 并记录审计日志 |
| P0-8 并发安全 | `fix(storage): make subscription and portfolio persistence concurrency-safe` | `backend/services/subscription_service.py`, `backend/services/portfolio_store.py`, `backend/tests/test_persistence_concurrency.py` | 订阅写入使用 temp + `os.replace`; portfolio SQLite 每操作连接 + 显式事务；50 并发测试覆盖 |
| P0-9 compose E2E | `test(integration): add compose-backed e2e smoke gate` | `.github/workflows/ci.yml`, `frontend/e2e-compose/smoke.spec.ts`, `frontend/playwright.compose.config.ts` | 新增 `e2e-compose` job；老 mock E2E 更名为 `e2e-frontend-mock` |
| P0-10 依赖与供应链 | `chore(deps): pin python dependencies and add supply-chain gates` | `requirements.in`, `requirements.txt`, `requirements-dev.txt`, `scripts/check_requirements_lock.py`, `.github/workflows/ci.yml`, `README.md` | `requirements.txt` 直接依赖全 pinned；CI 运行 lock check、`pip-audit`、CycloneDX SBOM |

## 回滚原则

每个条目均按建议提交标题拆分后可单独回滚。若未拆分提交，建议按上表文件集合分组回滚；其中 P0-2、P0-5、P0-6、P0-7 共享 `backend/security/auth.py` 和 principal 语义，回滚时需一起评估接口权限边界。喵～
