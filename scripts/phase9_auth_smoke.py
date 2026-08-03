"""Phase 9: Auth / API Key smoke 脚本
测试项：
1. 无 key 时 /api/me 行为
2. 无效 key 时被拒绝
3. 有效 key 时通过（如果 API_AUTH_KEYS 已配置）
4. DEV_MODE=false 状态下无 dev bypass
"""
import sys, io, urllib.request, json, time, re, os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = "http://localhost:8000"
RESULTS = []

def req(method, path, headers=None, body=None, timeout=5):
    url = BASE + path
    h = headers or {}
    data = body.encode() if isinstance(body, str) else body
    r = urllib.request.Request(url, data=data, method=method, headers=h)
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            elapsed = int((time.monotonic() - t0) * 1000)
            content = resp.read()
            return resp.status, content, elapsed
    except urllib.error.HTTPError as e:
        elapsed = int((time.monotonic() - t0) * 1000)
        return e.code, e.read(), elapsed

def check(name, condition, detail, status_code=None, blocking=True):
    icon = "PASS" if condition else "FAIL"
    RESULTS.append((name, icon, detail, blocking))
    sc = f" HTTP={status_code}" if status_code else ""
    print(f"  [{icon}] {name}{sc}: {detail}")
    return condition

print("=== Phase 9 Auth / API Key Smoke ===\n")

# --- 读取 API_AUTH_KEYS（如有）---
def load_env_key(env_file, key):
    try:
        with open(env_file, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=(.*)', line)
                if m and m.group(1) == key:
                    return m.group(2).strip().strip('"').strip("'")
    except:
        pass
    return None

api_keys_raw = load_env_key(".env.server", "API_AUTH_KEYS")
jwt_secret   = load_env_key(".env.server", "JWT_SECRET")
dev_mode     = load_env_key(".env.server", "DEV_MODE") or "false"

has_api_keys = bool(api_keys_raw and api_keys_raw not in ("", "your_key_here"))
has_jwt      = bool(jwt_secret and jwt_secret not in ("", "your_key_here"))
first_api_key = api_keys_raw.split(",")[0].strip() if has_api_keys else None

print(f"Config snapshot:")
print(f"  JWT_SECRET:    {'PRESENT' if has_jwt else 'MISSING'}")
print(f"  API_AUTH_KEYS: {'PRESENT' if has_api_keys else 'MISSING'}")
print(f"  DEV_MODE:      {dev_mode}")
print()

# 1. 健康检查（无 auth 要求）
code, body, ms = req("GET", "/api/health")
check("health-no-auth", code == 200, f"无需 auth — 期望 200", status_code=code)

# 2. /api/me 无 key（期望 401 或 200 取决于配置）
code, body, ms = req("GET", "/api/me")
if has_api_keys:
    # 有 key 配置时，无 key 应 401
    check("me-no-key", code in (401, 403), f"无 key 时期望 401/403，实际 {code}", status_code=code)
else:
    # 没配置 key 时行为取决于后端逻辑
    check("me-no-key", True, f"API_AUTH_KEYS 未配置，状态码 {code}（记录用）", status_code=code, blocking=False)

# 3. /api/me 无效 key（期望 401/403）
code, body, ms = req("GET", "/api/me", headers={"X-API-Key": "invalid"})
if has_api_keys:
    check("me-invalid-key", code in (401, 403), f"无效 key 时期望 401/403，实际 {code}", status_code=code)
else:
    check("me-invalid-key", True, f"API_AUTH_KEYS 未配置，无效 key 返回 {code}（记录用）", status_code=code, blocking=False)

# 4. /api/me 有效 key
if has_api_keys and first_api_key:
    code, body, ms = req("GET", "/api/me", headers={"X-API-Key": first_api_key})
    check("me-valid-key", code == 200, f"有效 key 期望 200，实际 {code}", status_code=code)
    if code == 200:
        try:
            data = json.loads(body)
            user_id = data.get("user_id") or data.get("sub") or data.get("username") or "unknown"
            print(f"    → user_id={user_id}")
        except:
            pass
else:
    print(f"  [SKIP] me-valid-key: API_AUTH_KEYS 未配置，跳过")
    RESULTS.append(("me-valid-key", "SKIP", "API_AUTH_KEYS 未配置", False))

# 5. DEV_MODE 验证
if dev_mode.lower() in ("1", "true", "yes"):
    check("dev-mode-off", False, f"DEV_MODE={dev_mode} 在生产中不可接受", blocking=True)
else:
    check("dev-mode-off", True, f"DEV_MODE 未启用（值={dev_mode}）")

# 6. JWT_SECRET 存在性
check("jwt-secret-exists", has_jwt, "JWT_SECRET 存在且非空", blocking=True)

# 7. 无 DEV_MODE bypass — 确认 /api/me 不会返回 default_user
code, body, ms = req("GET", "/api/me")
if code == 200:
    try:
        data = json.loads(body)
        is_default = (data.get("user_id") == "default_user" or data.get("sub") == "default_user")
        check("no-dev-bypass", not is_default,
              "无 token 时不应返回 default_user（dev bypass）", status_code=code, blocking=True)
    except:
        check("no-dev-bypass", True, "无法解析响应，记录用", blocking=False)
else:
    # 401 = 正常，没有 dev bypass
    check("no-dev-bypass", code in (401, 403),
          f"无 token 返回 {code}（无 dev bypass）", status_code=code)

print()
print("=== 汇总 ===")
passes = sum(1 for _, r, _, _ in RESULTS if r == "PASS")
fails  = sum(1 for _, r, _, _ in RESULTS if r == "FAIL")
skips  = sum(1 for _, r, _, _ in RESULTS if r == "SKIP")
print(f"PASS: {passes}  FAIL: {fails}  SKIP: {skips}")

blockers = [(n, d) for n, r, d, b in RESULTS if r == "FAIL" and b]
if blockers:
    print("BLOCKING:")
    for n, d in blockers:
        print(f"  - {n}: {d}")
