"""
Phase 9 最小发布确认 Smoke
包含：Compose config → 密钥检查 → 后端健康 → Auth → LLM → 核心 API → Notes 上传
"""
import sys, io, re, json, time, urllib.request, subprocess, os, tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

RESULTS = []

def log(name, ok, detail, ms=None, blocking=True):
    icon = "PASS" if ok else "FAIL"
    RESULTS.append((name, icon, detail, blocking))
    suffix = f" ({ms}ms)" if ms is not None else ""
    block = " [BLOCKING]" if (not ok and blocking) else ""
    print(f"  [{icon}] {name}{block}{suffix}: {detail}")
    return ok

# ─── 环境变量读取 ───────────────────────────────────────────────────────────
PLACEHOLDERS = {"your_key_here", "your-secret-here", "changeme", "placeholder", "xxx", ""}

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
                    env[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return env

env = load_env(".env.server")

def present(key):
    v = env.get(key, "")
    return bool(v) and v.lower() not in PLACEHOLDERS

JWT_SECRET    = env.get("JWT_SECRET", "")
API_AUTH_KEYS = env.get("API_AUTH_KEYS", "")
LLM_KEY       = env.get("OPENAI_COMPATIBLE_API_KEY", "")
LLM_BASE      = env.get("OPENAI_COMPATIBLE_API_BASE", "")
LLM_MODEL     = env.get("OPENAI_COMPATIBLE_MODEL", "")

has_jwt  = bool(JWT_SECRET) and JWT_SECRET.lower() not in PLACEHOLDERS and len(JWT_SECRET) >= 32
has_keys = bool(API_AUTH_KEYS) and API_AUTH_KEYS.lower() not in PLACEHOLDERS
has_llm  = bool(LLM_KEY) and LLM_KEY.lower() not in PLACEHOLDERS

print("=" * 60)
print("  Phase 9 最小发布确认 Smoke")
print("=" * 60)
print()

# ─── 1. Compose config ──────────────────────────────────────────────────────
print("[1] Compose config 验证")
for label, args in [
    ("base",  ["docker", "compose", "config", "--quiet"]),
    ("smoke", ["docker", "compose", "-f", "docker-compose.yml",
               "-f", "docker-compose.smoke.yml", "config", "--quiet"]),
]:
    t0 = time.monotonic()
    try:
        r = subprocess.run(args, capture_output=True, timeout=20)
        ms = int((time.monotonic()-t0)*1000)
        log(f"compose-config-{label}", r.returncode == 0,
            f"exit={r.returncode}" + (f" stderr={r.stderr.decode(errors='replace')[:100]}" if r.returncode != 0 else ""),
            ms, blocking=True)
    except Exception as ex:
        log(f"compose-config-{label}", False, str(ex), blocking=True)
print()

# ─── 2. 密钥存在性 ──────────────────────────────────────────────────────────
print("[2] 密钥存在性检查")
log("B1-JWT_SECRET",    has_jwt,  f"len={len(JWT_SECRET)}" if JWT_SECRET else "MISSING/EMPTY", blocking=True)
log("B2-API_AUTH_KEYS", has_keys, f"len={len(API_AUTH_KEYS)}" if API_AUTH_KEYS else "MISSING/EMPTY", blocking=True)
log("B3-LLM_KEY",       has_llm,  f"len={len(LLM_KEY)}" if LLM_KEY else "MISSING/EMPTY", blocking=True)
print()

# 若 B1/B2 缺失，无法启动真实 auth 后端；在测试值模式下继续
USE_TEST_CREDS = not (has_jwt and has_keys)
if USE_TEST_CREDS:
    TEST_JWT  = "phase9-minimal-smoke-jwt-secret-abcdefghijklmnopqrstuvwxyz01234"
    TEST_KEYS = "phase9-minimal-smoke-api-key-xyz"
    print(f"  ⚠ B1/B2 未配置 → 使用临时测试凭据运行后续 smoke（不代表生产状态）")
    print()
    SMOKE_JWT  = TEST_JWT
    SMOKE_KEYS = TEST_KEYS
else:
    SMOKE_JWT  = JWT_SECRET
    SMOKE_KEYS = API_AUTH_KEYS.split(",")[0].strip()

# ─── 3. 启动后端 ────────────────────────────────────────────────────────────
print("[3] 启动后端（uvicorn :8899）")
env_override = {
    **os.environ,
    "DEV_MODE": "false",
    "JWT_SECRET": SMOKE_JWT,
    "API_AUTH_KEYS": SMOKE_KEYS,
    "RAG_EMBEDDING": "hash",
    "RAG_V2_ALLOW_MEMORY_FALLBACK": "true",
}
proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "backend.api.main:app",
     "--host", "127.0.0.1", "--port", "8899", "--log-level", "warning"],
    env=env_override,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
BASE = "http://127.0.0.1:8899"
VALID_KEY = SMOKE_KEYS

# 等待启动
ready = False
for _ in range(20):
    time.sleep(0.8)
    try:
        with urllib.request.urlopen(BASE + "/health", timeout=2) as r:
            if r.status == 200:
                ready = True
                break
    except:
        pass

log("backend-startup", ready, f"PID={proc.pid} port=8899", blocking=True)
print()

if not ready:
    print("  后端启动失败，终止 smoke")
    proc.kill()
    sys.exit(1)

# ─── 辅助函数 ───────────────────────────────────────────────────────────────
def api(method, path, body=None, raw_body=None, raw_ct=None, extra_headers=None, timeout=8):
    url = BASE + path
    h = {"X-API-Key": VALID_KEY}
    if extra_headers:
        h.update(extra_headers)
    if raw_body is not None:
        h["Content-Type"] = raw_ct
        data = raw_body
    elif body is not None:
        h["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    else:
        data = None
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read()), int((time.monotonic()-t0)*1000)
    except urllib.error.HTTPError as e:
        return e.code, {}, int((time.monotonic()-t0)*1000)

# ─── 4. 健康 / Auth ─────────────────────────────────────────────────────────
print("[4] 健康检查 / Auth")
code, data, ms = api("GET", "/health")
log("health",     code == 200, f"HTTP {code}", ms)

# /api/me 无 key → guest
req_no_key = urllib.request.Request(BASE + "/api/me")
with urllib.request.urlopen(req_no_key, timeout=5) as r:
    no_key_data = json.loads(r.read())
no_dev_bypass = no_key_data.get("user_id") != "default_user"
log("no-dev-bypass", no_dev_bypass, f"user_id={no_key_data.get('user_id')}", blocking=True)

# /api/me 有效 key → api_key 身份
code, data, ms = api("GET", "/api/me")
uid = data.get("user_id", "")
log("auth-api-key",  code == 200 and uid.startswith("api_"),
    f"HTTP {code} user_id={uid}", ms)

SESSION = f"private:{uid}:default"
print()

# ─── 5. 核心 API ─────────────────────────────────────────────────────────────
print("[5] 核心 API")
for label, method, path, body in [
    ("today",             "GET",  f"/api/today?session_id={SESSION}&user_id={uid}",         None),
    ("research-quality",  "GET",  f"/api/research-quality?session_id={SESSION}&user_id={uid}", None),
    ("what-changed",      "GET",  f"/api/what-changed?session_id={SESSION}&user_id={uid}",  None),
    ("portfolio-summary", "GET",  f"/api/portfolio/summary?session_id={SESSION}&user_id={uid}", None),
    ("watchlist",         "GET",  f"/api/user/watchlist?user_id={uid}",                     None),
    ("reports",           "GET",  f"/api/reports/index?session_id={SESSION}&user_id={uid}", None),
]:
    code, data, ms = api(method, path, body)
    log(label, code == 200, f"HTTP {code}", ms)
print()

# ─── 6. Notes 上传闭环 ───────────────────────────────────────────────────────
print("[6] Notes 上传闭环")
code, data, ms = api("POST", "/api/research-notes", {
    "session_id": SESSION, "user_id": uid,
    "title": "Phase9 minimal smoke", "content": "ok", "ticker": "TEST",
})
note_id = data.get("note_id", "") if code == 200 else ""
log("note-create", code == 200, f"HTTP {code} note_id={note_id}", ms)

if note_id:
    PNG = bytes([
        0x89,0x50,0x4E,0x47,0x0D,0x0A,0x1A,0x0A,
        0x00,0x00,0x00,0x0D,0x49,0x48,0x44,0x52,
        0x00,0x00,0x00,0x01,0x00,0x00,0x00,0x01,
        0x08,0x02,0x00,0x00,0x00,0x90,0x77,0x53,
        0xDE,0x00,0x00,0x00,0x0C,0x49,0x44,0x41,
        0x54,0x08,0xD7,0x63,0xF8,0xCF,0xC0,0x00,
        0x00,0x00,0x02,0x00,0x01,0xE2,0x21,0xBC,
        0x33,0x00,0x00,0x00,0x00,0x49,0x45,0x4E,
        0x44,0xAE,0x42,0x60,0x82
    ])
    BND = b"MinimalSmokeBnd"
    CRLF = b"\r\n"
    mp = (b"--"+BND+CRLF
          +b'Content-Disposition: form-data; name="file"; filename="s.png"'+CRLF
          +b"Content-Type: image/png"+CRLF+CRLF
          +PNG+CRLF+b"--"+BND+b"--"+CRLF)
    code, data, ms = api(
        "POST",
        f"/api/research-notes/{note_id}/images?session_id={SESSION}&user_id={uid}",
        raw_body=mp, raw_ct=f"multipart/form-data; boundary={BND.decode()}",
    )
    img_url = data.get("url") or data.get("image_url") or "" if code == 200 else ""
    log("image-upload", code == 200, f"HTTP {code} url={img_url}", ms)

    if img_url:
        access_url = BASE + img_url if img_url.startswith("/") else img_url
        req_img = urllib.request.Request(access_url, headers={"X-API-Key": VALID_KEY})
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req_img, timeout=5) as r:
                sz = len(r.read())
                ms2 = int((time.monotonic()-t0)*1000)
                log("image-access", r.status == 200, f"HTTP {r.status} bytes={sz}", ms2)
        except Exception as ex:
            log("image-access", False, str(ex))

    # 删除测试 note
    code, _, ms = api("DELETE", f"/api/research-notes/{note_id}?session_id={SESSION}&user_id={uid}")
    log("note-cleanup", code in (200, 204), f"HTTP {code}", ms, blocking=False)
print()

# ─── 7. LLM smoke ────────────────────────────────────────────────────────────
print("[7] LLM smoke")
if not has_llm or not LLM_BASE:
    log("B3-llm-key", False, "OPENAI_COMPATIBLE_API_KEY 或 API_BASE 未配置", blocking=True)
else:
    payload = json.dumps({
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": "Reply with exactly one word: OK"}],
        "max_tokens": 5, "temperature": 0,
    }).encode()
    endpoint = LLM_BASE.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint = endpoint + "/chat/completions"
    req_llm = urllib.request.Request(
        endpoint, data=payload, method="POST",
        headers={"Authorization": f"Bearer {LLM_KEY}", "Content-Type": "application/json", "User-Agent": "FinSight/1.0"},
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req_llm, timeout=30) as resp:
            ms = int((time.monotonic()-t0)*1000)
            result = json.loads(resp.read())
            content = result["choices"][0]["message"]["content"].strip()
            log("B3-llm-call", True, f"model={LLM_MODEL} reply='{content}'", ms)
    except urllib.error.HTTPError as e:
        ms = int((time.monotonic()-t0)*1000)
        body_err = e.read().decode(errors="replace")[:150]
        log("B3-llm-call", False, f"HTTP {e.code}: {body_err}", ms, blocking=True)
    except Exception as ex:
        log("B3-llm-call", False, str(ex), blocking=True)
print()

# ─── 关闭测试后端 ────────────────────────────────────────────────────────────
proc.terminate()
try:
    proc.wait(timeout=5)
except:
    proc.kill()

# ─── 汇总 ────────────────────────────────────────────────────────────────────
passes   = sum(1 for _, r, _, _ in RESULTS if r == "PASS")
fails    = sum(1 for _, r, _, _ in RESULTS if r == "FAIL")
blockers = [(n, d) for n, r, d, b in RESULTS if r == "FAIL" and b]

print("=" * 60)
print(f"  PASS: {passes}   FAIL: {fails}")
print()

if USE_TEST_CREDS:
    print("  注：B1/B2 使用临时测试凭据运行，不代表生产状态")

if not blockers:
    print("  最终状态：✅ READY")
    print("  所有阻塞项已解除，可以发布。")
else:
    print("  最终状态：🟠 READY_WITH_BLOCKERS")
    print("  以下阻塞项未解除：")
    for n, d in blockers:
        print(f"    - {n}: {d}")
print("=" * 60)
