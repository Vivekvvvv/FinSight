# Phase 7 发布候选报告

**日期**: 2026-06-08  
**版本**: v1.0.0-rc.1  
**结论**: 🟡 **READY_WITH_NOTES** — 可发布候选，但有非阻塞注意事项

---

## 一、版本状态

| 项目 | 状态 |
|------|------|
| 版本号 | v1.0.0-rc.1 |
| Git 状态 | 本地开发快照（未 push） |
| 后端语言 | Python 3.12 / FastAPI |
| 前端框架 | Vue 3 + Vite 7.3 + TypeScript |
| 数据库 | SQLite（dev/smoke）/ PostgreSQL pgvector（prod） |
| RAG 后端 | hash embedding（smoke）/ BGE-M3（prod） |

---

## 二、Phase 4/5/6/7 完成摘要

### Phase 4: Evidence-Driven Research Experience（完成）
- Portfolio Risk Lens（三维风险评估）
- Research Notebook（笔记 + 图片上传）
- Timeline Aggregation（统一事件聚合）
- What Changed（规则引擎，7 大规则）
- Research Quality Calibration（100 分制健康分）

### Phase 5: Stability（完成）
- 性能基准测试（P95 < 1s）
- 安全验收（路径遍历防护、API 认证）
- Plan/Entitlements 门控（enforce_feature + enforce_quota）
- Release Gate 脚本

### Phase 6: E2E 稳定化（完成）
- E2E 测试从 22 失败 → **0 失败，48/48 全绿**
- 建立统一 API Mock Helper（apiMocks.ts）
- 修复多 API 并发加载模式的 mock 缺失

### Phase 7: 发布候选准备（本阶段，完成）
- 环境变量矩阵审计（PHASE7_ENV_MATRIX.md）
- Compose config 验证（3 种模式全部通过）
- API Smoke 测试（12/12 通过）
- 修复阻塞 Bug：`require_matching_identity` 调用方式不兼容
- 图片上传完整验证（上传/访问/安全防护）
- 性能复测（P95 全部 < 30ms）

---

## 三、测试矩阵

| 测试类型 | 结果 | 详情 |
|---------|------|------|
| 后端单元测试 | ✅ 通过 | Phase 4: 29/29 |
| TypeScript 类型检查 | ✅ 0 错误 | vue-tsc --noEmit |
| 前端构建 | ✅ 成功 | Vite 6.31s |
| E2E Playwright | ✅ **48/48** | pages.spec.ts 全绿 |
| API Smoke | ✅ 12/12 | 含修复后的 research-quality + what-changed |
| 性能复测 | ✅ P95 < 30ms | 8 个核心接口 |
| 图片上传 | ✅ 完整通过 | 上传/访问/路径遍历防护 |
| Compose config | ✅ 3/3 | base + dev + smoke 全部解析成功 |

---

## 四、已知风险与注意事项

### 非阻塞注意事项（NOTES）

| 项 | 说明 | 影响 |
|----|------|------|
| N1 | Docker daemon 在当前环境不可用，容器 smoke 未能实际运行 | 低：Compose 配置验证通过，本地 API smoke 全通过 |
| N2 | 行情 API 无 key 时 `/api/quote/*` 超时，前端需显示合理错误态 | 低：E2E mock 测试已覆盖，Playwright 48/48 验证 |
| N3 | BGE-M3 模型首次启动约 2-5 分钟（模型下载 ~2GB）| 中：smoke.yml 用 `RAG_EMBEDDING=hash` 绕过，prod 需预热 |
| N4 | DEV_MODE 下 `principal.user_id` 固定为 `default_user`，prod 关闭后需使用真实 API key | 低：DEV_MODE 有明确警告日志 |
| N5 | 行情数据依赖第三方 API（yfinance/FMP/Finnhub 等），无 key 时 Dashboard 报价卡不可用 | 中：功能可降级，空态有合理提示 |
| N6 | LLM 功能（Chat/Report 生成）需要 OpenAI-compatible API key | 高：核心功能，prod 必须配置 |
| N7 | PostgreSQL + pgvector 首次 `docker compose up` 需等待 healthcheck（约 30s） | 低：compose 已配置 depends_on healthy |

### 已修复的阻塞 Bug（Phase 7 发现）

| Bug | 影响接口 | 修复状态 |
|-----|---------|---------|
| `require_matching_identity` 位置参数调用方式与 keyword-only 签名不兼容 | `/api/research-quality` + `/api/what-changed` 返回 500 | ✅ 已修复 |

---

## 五、发布前人工确认项

| 确认项 | 状态 | 说明 |
|--------|------|------|
| 配置 `.env.server` 真实密钥 | ⬜ 待人工 | OPENAI_COMPATIBLE_API_KEY 等 |
| 确认 CORS_ALLOW_ORIGINS 设置正确 | ⬜ 待人工 | prod 不得使用 `*` |
| 确认 DEV_MODE 未设置 | ⬜ 待人工 | prod 必须关闭 |
| 确认 API_AUTH_ENABLED=true | ⬜ 待人工 | prod 安全要求 |
| Docker daemon 可用时执行 compose smoke | ⬜ 待人工 | 参见 PHASE7_SMOKE_REPORT.md |
| 真实浏览器手动验收 | ⬜ 待人工 | 参见 PHASE7_MANUAL_ACCEPTANCE.md |
| BGE-M3 模型预热测试 | ⬜ 待人工 | 首次启动需 2-5 分钟 |
| 配置 SMTP（可选）| ⬜ 待人工 | 邮件告警功能 |

---

## 六、发布候选结论

### 🟡 READY_WITH_NOTES

**理由**：

**支持发布**：
- E2E 全绿（48/48），覆盖所有主要用户流程
- API Smoke 全通过（12/12），包含修复后的所有接口
- 性能达标（P95 < 30ms，远超 1s 目标）
- 安全防护有效（路径遍历、API 认证）
- Compose 配置验证通过（3 种模式）
- Phase 4/5/6/7 功能完整交付

**注意事项（非阻塞）**：
- Docker 实际容器 smoke 受当前环境限制未完整执行，需在 Docker 可用环境补做
- 核心功能（LLM/行情数据）依赖外部 API key，需配置后才能使用
- BGE-M3 首次启动延迟（prod 需预热策略）

**不推荐 BLOCKED 的理由**：
- 所有核心代码路径已通过本地等效验证
- 阻塞 Bug（research-quality/what-changed 500）已修复
- 已知风险均有缓解措施或明确文档

---

## 七、发布后推荐步骤

1. 配置 `.env.server` 真实密钥
2. 在 Docker 可用环境执行 `docker compose -f docker-compose.yml -f docker-compose.smoke.yml up -d --build`
3. 验证 `http://localhost:18080/health`
4. 执行 `scripts/phase7_api_smoke.py`（指向 18080 端口）
5. 进行真实浏览器手动验收
6. 无问题则切换到生产 compose（无 smoke.yml，使用 :80 端口）

---

## 附：文档索引

| 文档 | 内容 |
|------|------|
| PHASE7_ENV_MATRIX.md | 环境变量矩阵（10 类别完整审计）|
| PHASE7_COMPOSE_VALIDATION.md | Compose 配置验证（3 种模式）|
| PHASE7_SMOKE_REPORT.md | Docker Smoke 报告（含环境限制说明）|
| PHASE7_API_SMOKE_REPORT.md | API Smoke 测试（12/12 通过）|
| PHASE7_MANUAL_ACCEPTANCE.md | 手动验收清单 |
| PHASE7_UPLOAD_SMOKE_REPORT.md | 图片上传验证 |
| PHASE7_PERFORMANCE_RECHECK.md | 性能复测（P95 < 30ms）|
| scripts/phase7_api_smoke.py | API Smoke 脚本 |
