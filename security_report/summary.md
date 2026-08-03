# FinSight 安全审计摘要

审计日期：2026-08-03
审计基线：`91281dd`（工作区包含 Compose 运行时最小权限加固的未提交修复）

## 结论

本轮完成了生产 Python 与 Node 依赖实时审计、Python/多语言静态分析、凭据扫描、SQL 注入与 SSRF 候选复核、访问控制回归、Docker 文件系统与真实镜像审计、容器运行探针，以及测试输出卫生清理。

在已执行的检查范围内：

- 生产 Python 完整传递依赖图：0 个已知漏洞。
- 前端 npm 依赖：0 个已知漏洞。
- Trivy 文件系统扫描：0 个依赖漏洞、0 个凭据发现、0 个配置发现。
- Bandit：0 个 High，31 个 Medium；Medium 均已人工复核为固定 SQL/URL、服务监听或 SSRF 防护字面量。
- Semgrep：50 个候选已复核；GitHub Actions 可变标签告警已从 26 降至 0。
- 密钥扫描器：扫描 1328 个文件，0 个发现。
- Gitleaks：工作区 6 个、Git 历史 20 个候选，均为测试哨兵或文档占位符，未发现真实凭据。
- SSRF 与访问控制相关回归：81 passed。
- 后端全量回归：4227 passed，10 skipped；升级依赖 overlay 结果相同，另有 1 条 Starlette 弃用预告。
- 前端 `npm ci`、typecheck、build 均通过。
- 前端生产镜像：非 root UID 101，健康检查与 HTTP 200 通过；Trivy 为 0 个漏洞、0 个凭据发现、0 个配置发现。
- 后端生产镜像：非 root UID 999，核心科学计算与 PostgreSQL 依赖导入、健康检查、HTTP 200、`/app/data` 写入均通过。
- 后端生产镜像：Trivy 为 4 个 Critical、19 个 High；均来自 Debian 13.6 基础层，当前扫描数据库未提供修复版本。Python 依赖层为 0 个漏洞，镜像为 0 个凭据发现、0 个配置发现。
- PostgreSQL 生产镜像：固定 pgvector 基础 digest，构建时升级到 PostgreSQL 16.14，保留 pgvector 0.8.2，并移除 gosu 后以 UID 999 启动。Trivy 从旧缓存镜像的 24 Critical / 67 High 降至 19 / 31，剩余 Critical/High 均无可用修复版本。

这不表示系统已被证明“绝对安全”。本轮验证的是本地构建的临时镜像；现有运行中的正式容器、服务器 SSH/防火墙和生产环境权限不在本次授权范围内。

## 已完成修复

- 升级生产 Python 依赖并移除未使用的 `litellm`、`chromadb`；将仅评测使用的 Ragas 移入开发依赖。
- 更新前端 lockfile，消除 npm 审计发现的 8 个漏洞。
- 将 `backend/requirements.txt` 收敛为引用根生产依赖清单，消除第二套旧锁定造成的 12 条 Trivy 公告。
- 将 `requirements.in` 与已审计的根锁定清单同步，确保未来重新生成依赖时不会带回 Ragas、LiteLLM、ChromaDB 或旧漏洞版本。
- 为非安全用途的 MD5/SHA1 调用显式设置 `usedforsecurity=False`，Bandit High 从 9 降至 0。
- 后端生产镜像改用非 root 用户，并排除测试、文档和脚本进入构建上下文。
- 后端生产镜像改为 builder/runtime 双阶段构建，构建工具不再进入 runtime；删除未使用的系统级 `setuptools`、两份 pip 安装器与仅供健康检查使用的 curl，High 从 27 降至 19，Python 镜像依赖漏洞归零。
- 前端 Nginx 改用非 root 用户和容器内 8080 端口，并补齐 `/run` 写权限；宿主端口保持不变，Trivy `DS-0002` 已关闭。
- Python、Node 与 Nginx 基础镜像固定到本轮实际验证的完整 digest；由于 Docker Hub 在当前网络不可达，构建验证通过 build arg 使用 AWS Docker Official Images 镜像完成。
- 同步更新 Python/Vue 切换映射验证器的前端容器端口断言为 8080，修复 `412906e` 中 Compose 已变更但门禁仍检查端口 80 的回归。
- Compose 三个服务均启用只读根文件系统与 `no-new-privileges`；前后端额外 drop ALL capabilities，并仅为已确认写目录配置 tmpfs 或命名卷。后端 Compose 健康检查同步改用 Python 标准库，不再依赖已从 runtime 移除的 curl。
- 隔离运行探针确认 Postgres 可初始化并写表，前后端在最小权限下 healthy；三容器链路经 Nginx 反代访问后端 `/health` 返回 HTTP 200。
- PostgreSQL 改由独立 `docker/postgres.Dockerfile` 构建：基础 pgvector 镜像固定 digest，应用当前 Debian/PostgreSQL 包更新，删除 gosu，并以非 root `postgres` 用户启动。pgvector 扩展创建、向量写入与距离查询均通过。
- 26 个 GitHub Actions 引用全部固定到当前官方标签对应的完整 commit SHA，并保留版本注释。
- 删除测试和评测脚本中的异常原文输出与 `traceback.print_exc()`，新增 AST 回归门禁。
- 将 smoke 脚本、CI 和文档中的假凭据改为环境变量或明确占位符。

## 未关闭风险

### Critical：后端基础镜像保留 4 条无修复版本公告

- 证据：`Dockerfile` 固定的 Python 3.11 slim / Debian 13.6 基础层；`trivy-backend-hardened-final-image.json` 命中 `perl-base` 的 4 条 Critical，Trivy 的 `FixedVersion` 均为空。
- 影响：这些问题涉及正则表达式、归档路径与反序列化处理；只有攻击者能够触发基础层对应 Perl 功能时才形成可利用路径，应用当前没有主动调用 Perl，但镜像内仍存在受影响组件。
- 建议：持续跟踪 Debian 13 安全更新并在修复版本发布后重建镜像；部署时保持非 root、最小权限和受控输入，降低基础层漏洞的可利用性。
- 状态：上游暂无可安装修复版本。对照扫描官方 Python 3.11 slim-bookworm 得到 6 Critical / 20 High，风险更高，因此未降级基础镜像。

### High：后端基础镜像保留 19 条无修复版本公告

- 证据：同一镜像扫描中，`util-linux`、`ncurses`、`perl-base`、`gzip` 与 `libacl` 等基础包合计 19 条 High，Trivy 的 `FixedVersion` 均为空。
- 影响：潜在影响包括内存破坏、路径遍历、任意文件修改与拒绝服务；应用未直接暴露这些命令行工具，但受影响库仍存在于运行层。
- 建议：保持 digest 固定并定期刷新 Trivy 数据库复扫；Debian 发布修复后更新 digest。不要以删除 dpkg 必需基础包的方式制造不可维护镜像。
- 状态：上游暂无可安装修复版本；本轮已消除所有具有修复版本的 Critical/High。

### Critical/High：PostgreSQL 基础镜像保留 19/31 条无修复版本公告

- 证据：`docker/postgres.Dockerfile` 固定的 pgvector pg16 digest；`trivy-postgres-hardened-image.json` 报告 19 个 Critical、31 个 High，所有 Critical/High 的 `FixedVersion` 均为空。
- 影响：主要来自 Debian 12 的 Perl、SQLite、XML、zlib、util-linux 与 ncurses 等基础组件。PostgreSQL 网络接口不直接调用大部分相关命令行能力，但受影响组件仍存在于镜像层。
- 建议：Docker Hub 恢复后重新拉取并扫描上游 pg16 tag；只有新基线风险更低且 pgvector 回归通过时才更新 digest。持续以非 root、只读根文件系统和隔离网络降低可利用性。
- 状态：已升级当前仓库可获得的全部包并移除 gosu；旧镜像中 5 个可修复 Critical、36 个可修复 High 已消除，剩余项暂无可安装修复版本。

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

- Trivy 漏洞库从官方 GHCR 实时下载成功；在线 misconfiguration checks bundle 下载失败，扫描回退到 Trivy 0.72.0 内嵌规则。
- Docker Hub registry 与 API 在本轮网络中不可达，无法证明缓存的 pgvector tag 是上游实时最新；报告仅对固定 digest 与其派生镜像负责。
- 后端改为非 root 后，已有命名卷可能仍由 root 拥有；上线前需在维护窗口迁移 `backend_data`、`backend_logs`、`model_cache` 的属主。
- 本轮只构建并验证了临时 `hardened-verify` 镜像，没有替换当前运行中的正式容器或命名卷。
- 前端 Nginx 启动要求 Compose DNS 能解析 `backend`；独立探针通过等价 host 映射验证，Compose 部署本身提供该服务名。
- Starlette TestClient 提示未来迁移到 `httpx2`，当前不影响运行。

## 原始报告

本地原始扫描产物位于 `C:/tmp/FinSight-security-scan-2/`，包括 pip-audit、npm audit、Bandit、Semgrep、Gitleaks、Trivy、前后端镜像扫描与密钥扫描 JSON。该目录不提交到仓库。
