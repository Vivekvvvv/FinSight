"""Phase 9: LLM 最小调用 smoke"""
import sys, io, urllib.request, json, time, os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 读取配置
import re
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
    except:
        pass
    return env

# 只读取 .env.server，不读 .env（避免 DEV key）
env = load_env(".env.server")

API_KEY   = env.get("OPENAI_COMPATIBLE_API_KEY", "")
BASE_URL  = env.get("OPENAI_COMPATIBLE_API_BASE", "")
MODEL     = env.get("OPENAI_COMPATIBLE_MODEL", "")
LLM_BASE  = env.get("LLM_API_BASE", "")

print("=== Phase 9 LLM 最小调用 Smoke ===\n")
print(f"  OPENAI_COMPATIBLE_API_KEY: {'PRESENT' if API_KEY else 'MISSING'} (len={len(API_KEY)})")
print(f"  OPENAI_COMPATIBLE_API_BASE: {BASE_URL or 'MISSING'}")
print(f"  OPENAI_COMPATIBLE_MODEL: {MODEL or 'MISSING'}")
print()

RESULTS = []

def log(name, ok, detail, ms=0):
    RESULTS.append((name, "PASS" if ok else "FAIL", detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} ({ms}ms): {detail}")

if not API_KEY or not BASE_URL:
    print("  [SKIP] LLM smoke: API_KEY or BASE_URL missing in .env.server")
    RESULTS.append(("llm-smoke", "SKIP", "credentials not configured"))
else:
    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": "Reply with exactly one word: OK"}],
        "max_tokens": 5,
        "temperature": 0,
    }).encode("utf-8")

    req = urllib.request.Request(
        BASE_URL,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        }
    )

    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            ms = int((time.monotonic()-t0)*1000)
            result = json.loads(resp.read())
            content = result["choices"][0]["message"]["content"].strip()
            tokens = result.get("usage", {})
            log("llm-call", True, f"model={MODEL} response='{content}' tokens={tokens}", ms)
            log("llm-valid-response", bool(content), f"非空响应: '{content}'", 0)
    except urllib.error.HTTPError as e:
        ms = int((time.monotonic()-t0)*1000)
        body_err = e.read().decode(errors="replace")[:200]
        log("llm-call", False, f"HTTP {e.code}: {body_err}", ms)
    except Exception as ex:
        ms = int((time.monotonic()-t0)*1000)
        log("llm-call", False, str(ex), ms)

# 也通过后端 /api/chat 测试
print()
print("[via backend /api/chat]")
BASE_API = "http://localhost:8766"
API_AUTH = os.environ.get("API_AUTH_SMOKE_KEY", "")
if not API_AUTH:
    raise SystemExit("API_AUTH_SMOKE_KEY is required")
UID = "api_292e6a1e82c561d4"
SESSION = f"private:{UID}:default"

chat_body = json.dumps({
    "message": "Reply with exactly one word: READY",
    "session_id": SESSION,
    "user_id": UID,
    "stream": False,
}).encode()

req2 = urllib.request.Request(
    BASE_API + "/api/chat",
    data=chat_body,
    method="POST",
    headers={
        "X-API-Key": API_AUTH,
        "Content-Type": "application/json",
    }
)
t0 = time.monotonic()
try:
    with urllib.request.urlopen(req2, timeout=30) as resp:
        ms = int((time.monotonic()-t0)*1000)
        data = json.loads(resp.read())
        reply = data.get("reply") or data.get("content") or data.get("message") or str(data)[:100]
        log("chat-endpoint", True, f"HTTP 200 reply_len={len(reply)} ({ms}ms)", ms)
except urllib.error.HTTPError as e:
    ms = int((time.monotonic()-t0)*1000)
    body_err = e.read().decode(errors="replace")[:200]
    log("chat-endpoint", False, f"HTTP {e.code}: {body_err}", ms)
except Exception as ex:
    ms = int((time.monotonic()-t0)*1000)
    log("chat-endpoint", False, str(ex), ms)

print()
print("=== 汇总 ===")
passes = sum(1 for _, r, _ in RESULTS if r == "PASS")
fails  = sum(1 for _, r, _ in RESULTS if r == "FAIL")
skips  = sum(1 for _, r, _ in RESULTS if r == "SKIP")
print(f"PASS: {passes}  FAIL: {fails}  SKIP: {skips}")

raise SystemExit(1 if fails else 0)
