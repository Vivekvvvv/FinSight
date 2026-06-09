"""Phase 9: 密钥存在性检查 — 不打印真实值"""
import re, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KEYS = [
    # P0 安全
    ("JWT_SECRET",                    "P0-security"),
    ("API_AUTH_KEYS",                 "P0-security"),
    ("DEV_MODE",                      "P0-security"),
    # LLM
    ("OPENAI_API_KEY",                "LLM"),
    ("OPENAI_COMPATIBLE_API_KEY",     "LLM"),
    ("OPENAI_COMPATIBLE_API_BASE",    "LLM"),
    ("OPENAI_COMPATIBLE_MODEL",       "LLM"),
    ("GEMINI_PROXY_API_KEY",          "LLM"),
    ("GEMINI_PROXY_API_BASE",         "LLM"),
    ("DEEPSEEK_API_KEY",              "LLM"),
    ("LLM_API_BASE",                  "LLM"),
    # 行情
    ("FMP_API_KEY",                   "market-optional"),
    ("FINNHUB_API_KEY",               "market-optional"),
    ("ALPHA_VANTAGE_API_KEY",         "market-optional"),
    ("POLYGON_API_KEY",               "market-optional"),
    # 搜索
    ("TAVILY_API_KEY",                "search-optional"),
    ("JINA_READER_BASE_URL",          "search-optional"),
    # 数据库
    ("DATABASE_URL",                  "DB"),
    ("POSTGRES_USER",                 "DB"),
    ("POSTGRES_PASSWORD",             "DB"),
    ("POSTGRES_DB",                   "DB"),
    # 应用
    ("CORS_ORIGINS",                  "app"),
    ("RAG_BACKEND",                   "app-optional"),
    ("RAG_EMBEDDING",                 "app-optional"),
    ("UPLOAD_DIR",                    "app-optional"),
    # SMTP
    ("SMTP_HOST",                     "smtp-optional"),
    ("SMTP_USER",                     "smtp-optional"),
    ("SMTP_PASSWORD",                 "smtp-optional"),
    # 前端
    ("VITE_API_BASE_URL",             "frontend"),
    # Supabase
    ("SUPABASE_URL",                  "supabase-optional"),
    ("SUPABASE_ANON_KEY",             "supabase-optional"),
]

PLACEHOLDERS = {"your_key_here", "your-secret-here", "changeme", "placeholder", "xxx"}

with open(".env.server", encoding="utf-8", errors="replace") as f:
    lines = f.readlines()

env = {}
for line in lines:
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=(.*)', line)
    if m:
        k, v = m.group(1), m.group(2).strip().strip('"').strip("'")
        env[k] = v

print(f"=== Phase 9 密钥存在性检查 ===")
print(f"Total vars in .env.server: {len(env)}")
print()

results = {}
for key, category in KEYS:
    val = env.get(key)
    if val is None:
        status = "MISSING"
    elif val == "" or val.lower() in PLACEHOLDERS:
        status = "EMPTY/PLACEHOLDER"
    else:
        l = len(val)
        # 额外检测：JWT_SECRET 需要足够长
        if key == "JWT_SECRET" and l < 32:
            status = f"PRESENT_BUT_SHORT (len={l}, need>=32)"
        elif key == "API_AUTH_KEYS" and l < 8:
            status = f"PRESENT_BUT_SHORT (len={l})"
        else:
            status = f"PRESENT (len={l})"
    results[key] = (status, category)
    print(f"  [{category:<20}] {key:<42} {status}")

print()
# 统计阻塞项
blocking = [k for k, (s, c) in results.items() if c.startswith("P0") and "PRESENT" not in s]
llm_ok = any("PRESENT" in results.get(k, ("",))[0] for k in [
    "OPENAI_API_KEY", "OPENAI_COMPATIBLE_API_KEY", "GEMINI_PROXY_API_KEY", "DEEPSEEK_API_KEY"
])
if not llm_ok:
    blocking.append("LLM_KEY (any)")

print("=== 阻塞项（B1/B2/B3）===")
if blocking:
    for b in blocking:
        print(f"  BLOCKING: {b}")
else:
    print("  无阻塞项 — 所有 P0 密钥已就绪")
