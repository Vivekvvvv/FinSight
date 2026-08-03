# FinSight 安全审计摘要

审计日期：2026-08-03
审计基线：`688fd54`（工作区包含前端非 root 的未提交修复）

## 结论

本轮完成了生产 Python 与 Node 依赖实时审计、Python/多语言静态分析、凭据扫描、SQL 注入与 SSRF 候选复核、访问控制回归、Docker 文件系统配置审计，以及测试输出卫生清理。

在已执行的检查范围内：

- 生产 Python 完整传递依赖图：0 个已知漏洞。
- 前端 npm 依赖：0 个已知漏洞。
- Trivy 文件系统扫描：0 个依赖漏洞、0 个凭据发现、0 个配置发现。
- Bandit：0 个 High，31 个 Medium；Medium 均已人工复核为固定 SQL/URL、服务监听或 SSRF 防护字面量。
- Semgrep：50 个候选已复核；GitHub Actions 可变标签告警已从 26 降至 0。
- 密钥扫描器：扫描 1312 个文件，0 个发现。
- Gitleaks：工作区 6 个、Git 历史 20 个候选，均为测试哨兵或文档占位符，未发现真实凭据。
- SSRF 与访问控制相关回归：81 passed。
- 后端全量回归：4227 passed，10 skipped；升级依赖 overlay 结果相同，另有 1 条 Starlette 弃用预告。
- 前端 `npm ci`、typecheck、build 均通过。

这不表示系统已被证明“绝对安全”。镜像级扫描、运行中容器、服务器 SSH/防火墙和生产环境权限不在本地文件系统审计覆盖范围内。

## 已完成修复

- 升级生产 Python 依赖并移除未使用的 `litellm`、`chromadb`；将仅评测使用的 Ragas 移入开发依赖。
- 更新前端 lockfile，消除 npm 审计发现的 8 个漏洞。
- 将 `backend/requirements.txt` 收敛为引用根生产依赖清单，消除第二套旧锁定造成的 12 条 Trivy 公告。
- 将 `requirements.in` 与已审计的根锁定清单同步，确保未来重新生成依赖时不会带回 Ragas、LiteLLM、ChromaDB 或旧漏洞版本。
- 为非安全用途的 MD5/SHA1 调用显式设置 `usedforsecurity=False`，Bandit High 从 9 降至 0。
- 后端生产镜像改用非 root 用户，并排除测试、文档和脚本进入构建上下文。
- 前端 Nginx 改用非 root 用户和容器内 8080 端口；宿主端口保持不变，Trivy `DS-0002` 已关闭。
- 26 个 GitHub Actions 引用全部固定到当前官方标签对应的完整 commit SHA，并保留版本注释。
- 删除测试和评测脚本中的异常原文输出与 `traceback.print_exc()`，新增 AST 回归门禁。
- 将 smoke 脚本、CI 和文档中的假凭据改为环境变量或明确占位符。

## 未关闭风险

### High：开发依赖 Ragas 保留 2 条公告

- 证据：`requirements-dev.txt` 中 `ragas==0.2.15`；实时 pip-audit 命中 `PYSEC-2026-3046` 与 `PYSEC-2026-3047`。
- 影响：处理不受信任的多模态上下文时可能发生 SSRF 或任意本地文件读取。
- 建议：仅在隔离的离线评测环境使用，不接收用户输入、不挂载敏感目录；待上游发布覆盖两项问题的修复版后升级。若评测不再需要，直接移除。
- 状态：已从生产依赖隔离；其中一条公告当前无上游修复版本。

## 已复核候选

- SQL：Semgrep 12 个 Error 与 Bandit 11 个 B608 候选均使用固定结构、白名单标识符或参数绑定，未发现请求参数进入 SQL 结构。
- SSRF：Semgrep 15 个动态 URL 候选经调用链与 81 个安全回归复核，目标来自固定 smoke 地址、受约束部署配置或经过 URL/IP 校验与 DNS pinning。
- 凭据：Gitleaks 候选仅为脱敏测试哨兵、`YOUR_TOKEN` 等文档占位符；报告已 100% 脱敏。

## 覆盖缩减与运行风险

- Docker Desktop daemon 未启动，因此未执行 `docker build`、镜像层 CVE 扫描或运行时容器验证。
- Trivy 漏洞库从官方 GHCR 实时下载成功；在线 misconfiguration checks bundle 下载失败，扫描回退到 Trivy 0.72.0 内嵌规则。
- 基础镜像仍使用 tag 而非 digest，无法保证构建输入不可变。
- 后端改为非 root 后，已有命名卷可能仍由 root 拥有；上线前需在维护窗口迁移 `backend_data`、`backend_logs`、`model_cache` 的属主。
- Compose 尚未统一设置 `no-new-privileges`、capability drop 或只读根文件系统；需按 Postgres、后端和 Nginx 的写目录分别设计。
- Starlette TestClient 提示未来迁移到 `httpx2`，当前不影响运行。

## 原始报告

本地原始扫描产物位于 `C:/tmp/FinSight-security-scan-2/`，包括 pip-audit、npm audit、Bandit、Semgrep、Gitleaks、Trivy 与密钥扫描 JSON。该目录不提交到仓库。
