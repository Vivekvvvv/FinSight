"""Phase 8: External LLM API smoke test.

本脚本只从环境变量读取配置，不允许硬编码 API key。
"""
import sys, io, urllib.request, json, time, os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

API_KEY = os.getenv("OPENAI_COMPATIBLE_API_KEY", "").strip()
BASE_URL = os.getenv("OPENAI_COMPATIBLE_BASE_URL", "https://grok.jiuuij.de5.net/v1/chat/completions").strip()
MODEL = os.getenv("OPENAI_COMPATIBLE_MODEL", "grok-4.1-fast").strip()

if not API_KEY:
    raise SystemExit("Missing OPENAI_COMPATIBLE_API_KEY")

payload = json.dumps({
    "model": MODEL,
    "messages": [{"role": "user", "content": "Reply with exactly: SMOKE_OK"}],
    "max_tokens": 10,
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
        elapsed = (time.monotonic() - t0) * 1000
        result = json.loads(resp.read())
        content = result["choices"][0]["message"]["content"].strip()
        print(f"LLM_SMOKE: PASS")
        print(f"  model={MODEL}")
        print(f"  response='{content}'")
        print(f"  latency={elapsed:.0f}ms")
        print(f"  tokens_used={result.get('usage', {})}")
except urllib.error.HTTPError as e:
    elapsed = (time.monotonic() - t0) * 1000
    body = e.read().decode(errors="replace")
    print(f"LLM_SMOKE: FAIL HTTP {e.code} ({elapsed:.0f}ms)")
    print(f"  detail={body[:300]}")
except Exception as ex:
    print(f"LLM_SMOKE: FAIL — {ex}")
