# PHASE9_SECURITY_CONFIG_CHECK.md

**生成时间**：2026-06-09  
**阶段**：Phase 9 — 安全配置检查  
**结论**：PASS with WARNINGS（2 项 FAIL 为 B1/B2 密钥缺失，已在 SECRET_READINESS 记录；配置层无其他阻塞）

---

## 1. 检查结果

| # | 检查项 | 结果 | 说明 |
|---|--------|------|------|
| 1 | DEV_MODE | ✅ PASS | 未设置，默认 false；`is_dev_mode()` 返回 false |
| 2 | JWT_SECRET | ❌ FAIL（BLOCKING B1） | 缺失，任何 JWT 可被伪造 |
| 3 | API_AUTH_KEYS | ❌ FAIL（BLOCKING B2） | 缺失，API 无访问控制 |
| 4 | CORS 通配符 | ✅ PASS | 代码默认值为 localhost 列表，不含 `*` |
| 5 | VITE_API_BASE_URL | ⚠️ WARN | `http://localhost:8000`；Docker nginx 代理部署可接受，裸部署需改为实际域名 |
| 6 | 数据库配置 | ✅ PASS | POSTGRES_USER/PASSWORD/DB 均已配置 |
| 7 | RAG_EMBEDDING | ✅ PASS | `bge-m3`（生产模式，需确认模型已下载） |
| 8 | postgres 端口暴露 | ✅ PASS | `docker-compose.yml` 注释确认：postgres:5432 仅 compose-internal；宿主机暴露仅在 `docker-compose.dev.yml` |
| 9 | backend 端口暴露 | ✅ PASS | backend:8000 无直接宿主机映射，仅通过 nginx 访问 |
| 10 | UPLOAD_DIR | ✅ PASS | 路径遍历防护已在代码层验证（Phase 7） |
| 11 | 日志泄露扫描 | ✅ PASS | 静态扫描未发现 JWT_SECRET/API_AUTH_KEYS 被打印 |

---

## 2. CORS 详细分析

代码路径：`backend/api/main.py:411 _cors_allow_origins()`

```python
# 读取 CORS_ALLOW_ORIGINS 环境变量，默认值：
"http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174"
```

- 生产部署时设置 `CORS_ALLOW_ORIGINS=https://app.yourdomain.com`
- 代码已有通配符检测：`CORS_ALLOW_CREDENTIALS=true` 与 `*` 同时存在时自动禁用 credentials（防 CORS misconfiguration）

---

## 3. Port Exposure 详细分析

`docker-compose.yml` 头部注释：
```
# postgres:5432 are compose-internal by default.
# Use docker-compose.dev.yml for local host port exposure.
```

生产部署使用 `docker-compose.yml`（不加载 `.dev.yml`），端口暴露策略：
- frontend:80 → 宿主机（可配置为 80/443）
- backend:8000 → 仅 compose 内部（通过 nginx 代理）
- postgres:5432 → 仅 compose 内部

符合最小权限原则。

---

## 4. DEV_MODE 保护机制

`backend/security/auth.py:22`:
```python
def is_dev_mode() -> bool:
    return env_bool("DEV_MODE", "false")
```

生产主动保护：
- `main.py:695`: 如检测到 `DEV_MODE=true` 则输出 WARNING 日志
- auth bypass、rate limit 禁用、principal 固定等均只在 DEV_MODE=true 时激活
- 未设置等同于 false，无需显式配置

---

## 5. 非阻塞警告说明

| WARN 项 | 建议 |
|---------|------|
| `VITE_API_BASE_URL=localhost` | Docker nginx 代理部署不受影响（前端请求走相对路径）；直接访问后端场景需更新 |
| `CORS_ORIGINS` 未设置 | 本地开发可接受；生产部署前设置 `CORS_ALLOW_ORIGINS=https://实际域名` |

---

## 6. 安全配置总结

```
✅ 无 dev mode 后门
✅ 无 CORS 通配符
✅ 数据库不直接暴露
✅ 文件上传路径遍历防护已验证
✅ 日志无密钥泄露
❌ JWT_SECRET 缺失（B1 — 上线前必须解决）
❌ API_AUTH_KEYS 缺失（B2 — 上线前必须解决）
```
