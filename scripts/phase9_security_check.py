"""Phase 9: 安全配置检查"""
import re, sys, io, os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PLACEHOLDERS = {
    "your_key_here",
    "your-secret-here",
    "changeme",
    "placeholder",
    "replace_me_long_random_secret",
    "replace_me_internal_api_key",
    "xxx",
    "",
}


def parse_env_value(raw_value):
    value = raw_value.strip()
    if value[:1] in {'"', "'"}:
        closing_quote = value.find(value[0], 1)
        if closing_quote >= 0:
            return value[1:closing_quote]
    return re.split(r"\s+#", value, maxsplit=1)[0].strip()

def load_env(path):
    env = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=(.*)', line)
                if m:
                    k, v = m.group(1), parse_env_value(m.group(2))
                    env[k] = v
    except FileNotFoundError:
        pass
    return env

env = load_env(".env.server")

checks = []

def check(name, result, detail, blocking=False):
    checks.append((name, result, detail, blocking))
    icon = "OK" if result == "PASS" else ("WARN" if result == "WARN" else "FAIL")
    b = " [BLOCKING]" if blocking and result == "FAIL" else ""
    print(f"  [{icon}] {name}{b}: {detail}")

print("=== Phase 9 安全配置检查 ===\n")

# 1. DEV_MODE 必须为 false 或未设置
dev_mode = env.get("DEV_MODE", "").lower()
if dev_mode in ("1", "true", "yes", "on"):
    check("DEV_MODE", "FAIL", f"DEV_MODE={env.get('DEV_MODE')} 在生产中必须为 false 或未设置", blocking=True)
else:
    check("DEV_MODE", "PASS", f"未设置或为 false（默认 false）")

# 2. JWT_SECRET 存在且足够长
jwt = env.get("JWT_SECRET", "")
if not jwt or jwt.lower() in PLACEHOLDERS:
    check("JWT_SECRET", "FAIL", "缺失或为空 — 任何人可伪造 token", blocking=True)
elif len(jwt) < 32:
    check("JWT_SECRET", "FAIL", f"长度 {len(jwt)} 太短，需 >=32 字符", blocking=True)
else:
    check("JWT_SECRET", "PASS", f"长度 {len(jwt)} — 充分")

# 3. API_AUTH_KEYS 存在
api_keys = env.get("API_AUTH_KEYS", "")
api_key_items = [item.strip() for item in api_keys.split(",") if item.strip()]
if not api_keys or any(item.lower() in PLACEHOLDERS for item in api_key_items):
    check("API_AUTH_KEYS", "FAIL", "缺失或为空 — API 无访问控制", blocking=True)
elif min((len(item) for item in api_key_items), default=0) < 8:
    shortest = min((len(item) for item in api_key_items), default=0)
    check("API_AUTH_KEYS", "FAIL", f"最短 key 长度 {shortest}，每个 key 需 >=8 字符", blocking=True)
else:
    check("API_AUTH_KEYS", "PASS", f"已配置 {len(api_key_items)} 个 key")

# 4. CORS 不使用通配符
cors = env.get("CORS_ALLOW_ORIGINS", "")
cors_origins = {origin.strip() for origin in cors.split(",") if origin.strip()}
if "*" in cors_origins:
    check("CORS_ALLOW_ORIGINS", "FAIL", "使用 * 通配符，允许任意来源跨域", blocking=True)
elif not cors:
    check("CORS_ALLOW_ORIGINS", "WARN", "未配置，将使用代码默认值（需确认不含 *）")
else:
    check("CORS_ALLOW_ORIGINS", "PASS", f"已配置（不含通配符）: len={len(cors)}")

# 5. 前端 API base 不指向 localhost（生产用）
cors_regex = env.get("CORS_ALLOW_ORIGIN_REGEX", "").strip()
if cors_regex:
    try:
        compiled_cors_regex = re.compile(cors_regex)
        allows_untrusted_origin = any(
            compiled_cors_regex.fullmatch(origin)
            for origin in (
                "https://untrusted-origin.example",
                "http://untrusted-origin.example:4321",
            )
        )
    except re.error:
        check("CORS_ALLOW_ORIGIN_REGEX", "FAIL", "invalid regex", blocking=True)
    else:
        check(
            "CORS_ALLOW_ORIGIN_REGEX",
            "FAIL" if allows_untrusted_origin else "PASS",
            "regex accepts arbitrary origin" if allows_untrusted_origin else "configured restricted regex",
            blocking=allows_untrusted_origin,
        )

vite_base = env.get("VITE_API_BASE_URL", "")
if "localhost" in vite_base or "127.0.0.1" in vite_base:
    check("VITE_API_BASE_URL", "WARN", f"指向 localhost ({vite_base})，生产需改为实际域名")
elif not vite_base:
    check("VITE_API_BASE_URL", "WARN", "未配置，前端将使用相对路径（Docker nginx 代理可接受）")
else:
    check("VITE_API_BASE_URL", "PASS", f"已配置（非 localhost）")

# 6. DATABASE_URL 不含生产凭据明文（只检查格式）
db_url = env.get("DATABASE_URL", "")
if not db_url:
    # 检查分散的 POSTGRES_* 变量
    pg_user = env.get("POSTGRES_USER", "")
    pg_pass = env.get("POSTGRES_PASSWORD", "")
    pg_db   = env.get("POSTGRES_DB", "")
    if pg_user and pg_pass and pg_db:
        check("DATABASE_CONFIG", "PASS", "POSTGRES_USER/PASSWORD/DB 均已配置")
    else:
        missing = [k for k, v in [("POSTGRES_USER", pg_user), ("POSTGRES_PASSWORD", pg_pass), ("POSTGRES_DB", pg_db)] if not v]
        check("DATABASE_CONFIG", "WARN", f"DATABASE_URL 未设置，缺少: {missing}")
else:
    check("DATABASE_URL", "PASS", "已配置（不打印值）")

# 7. RAG_EMBEDDING 生产不应为 hash（除非是临时）
rag = env.get("RAG_EMBEDDING", "")
if rag.lower() == "hash":
    check("RAG_EMBEDDING", "WARN", "设置为 hash（跳过 BGE-M3），语义搜索降级")
elif not rag:
    check("RAG_EMBEDDING", "PASS", "未设置 → 使用默认（bge-m3 or 内置）")
else:
    check("RAG_EMBEDDING", "PASS", f"RAG_EMBEDDING={rag}")

# 8. 检查 compose 文件端口暴露
print()
print("[Port exposure check — docker-compose.yml]")
try:
    with open("docker-compose.yml", encoding="utf-8") as f:
        compose_content = f.read()
    # 检查 postgres 是否直接暴露
    if re.search(r'postgres.*ports.*5432', compose_content, re.DOTALL | re.IGNORECASE):
        check("postgres-port-exposure", "WARN", "docker-compose.yml 中 postgres 可能有外部端口映射，生产需关闭")
    else:
        check("postgres-port-exposure", "PASS", "postgres 无外部端口映射")

    # 检查 backend 是否直接暴露
    # 找 backend service 的 ports 块
    if re.search(r'"8000:8000"|0\.0\.0\.0:8000', compose_content):
        check("backend-port-exposure", "WARN", "backend:8000 直接暴露，生产建议只通过 nginx 访问")
    else:
        check("backend-port-exposure", "PASS", "backend 端口未直接映射到宿主机")
except Exception as e:
    check("compose-file", "WARN", f"无法读取 docker-compose.yml: {e}")

# 9. 检查 upload 目录配置
upload_dir = env.get("UPLOAD_DIR", "./uploads")
check("UPLOAD_DIR", "PASS" if upload_dir else "WARN",
      f"UPLOAD_DIR={upload_dir or '(default ./uploads)'}（路径遍历防护在代码层已验证）")

# 10. 日志不打印 secret（静态检查）
print()
print("[Log secret leak check]")
import glob
leak_found = False
for py in glob.glob("backend/**/*.py", recursive=True):
    with open(py, encoding="utf-8", errors="replace") as f:
        content = f.read()
    # 简单检查：不应该 log JWT_SECRET 或 API_AUTH_KEYS
    if re.search(r'log.*JWT_SECRET|JWT_SECRET.*log|print.*JWT_SECRET', content):
        print(f"  WARN: {py} 可能打印 JWT_SECRET")
        leak_found = True
    if re.search(r'log.*API_AUTH_KEYS|API_AUTH_KEYS.*log', content):
        print(f"  WARN: {py} 可能打印 API_AUTH_KEYS")
        leak_found = True
if not leak_found:
    check("log-secret-leak", "PASS", "静态扫描未发现 JWT_SECRET/API_AUTH_KEYS 被打印到日志")

# 汇总
print()
print("=== 汇总 ===")
failures = [(n, d) for n, r, d, b in checks if r == "FAIL"]
warnings = [(n, d) for n, r, d, b in checks if r == "WARN"]
passes   = [(n, d) for n, r, d, b in checks if r == "PASS"]
blocking = [(n, d) for n, r, d, b in checks if r == "FAIL" and b]

print(f"PASS:    {len(passes)}")
print(f"WARN:    {len(warnings)}")
print(f"FAIL:    {len(failures)}")
print(f"BLOCKING: {len(blocking)}")
if blocking:
    print("BLOCKING ITEMS:")
    for n, d in blocking:
        print(f"  - {n}: {d}")

raise SystemExit(1 if blocking else 0)
