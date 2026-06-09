"""Phase 9: Notes 创建 + 图片上传 smoke (non-DEV_MODE)"""
import sys, io, urllib.request, json, time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = "http://localhost:8766"
API_KEY = "phase9-test-key-abc123"
UID = "api_292e6a1e82c561d4"
SESSION = f"private:{UID}:default"

HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

def req(method, path, body=None, headers=None, raw_body=None, raw_ct=None, timeout=8):
    url = BASE + path
    h = {**(headers or HEADERS)}
    if raw_body is not None:
        h["Content-Type"] = raw_ct
        data = raw_body
    elif body is not None:
        data = json.dumps(body).encode()
    else:
        data = None
    r = urllib.request.Request(url, data=data, method=method, headers=h)
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read()), int((time.monotonic()-t0)*1000)
    except urllib.error.HTTPError as e:
        return e.code, {}, int((time.monotonic()-t0)*1000)

results = []
def log(name, ok, detail, ms=0):
    icon = "PASS" if ok else "FAIL"
    results.append((name, icon, detail))
    print(f"  [{icon}] {name} ({ms}ms): {detail}")

print("=== Phase 9 Notes Upload Smoke ===\n")

# 1. 创建 note (session_id + user_id 需在 body 里)
code, data, ms = req("POST", "/api/research-notes", {
    "session_id": SESSION,
    "user_id": UID,
    "title": "Phase 9 smoke note",
    "content": "Minimal note for smoke test",
    "ticker": "TEST",
    "tags": ["smoke"],
})
ok = code == 200
note_id = data.get("note_id", "") if ok else ""
log("note-create", ok, f"HTTP {code} note_id={note_id}", ms)

if not note_id:
    print("  Cannot continue without note_id")
    sys.exit(1)

# Minimal valid 1x1 PNG
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

# 2. 上传图片
BOUNDARY = b"Phase9SmokeBoundary"
CRLF = b"\r\n"
mpart_body = (
    b"--" + BOUNDARY + CRLF
    + b'Content-Disposition: form-data; name="file"; filename="phase9.png"' + CRLF
    + b"Content-Type: image/png" + CRLF + CRLF
    + PNG + CRLF
    + b"--" + BOUNDARY + b"--" + CRLF
)

code, data, ms = req(
    "POST",
    f"/api/research-notes/{note_id}/images?session_id={SESSION}&user_id={UID}",
    raw_body=mpart_body,
    raw_ct=f"multipart/form-data; boundary={BOUNDARY.decode()}",
)
ok = code == 200
img_url = data.get("url") or data.get("image_url") or data.get("path") if ok else ""
log("image-upload", ok, f"HTTP {code} url={img_url}", ms)

# 3. 访问图片 URL
if img_url:
    access_url = BASE + img_url if img_url.startswith("/") else img_url
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(urllib.request.Request(
            access_url, headers={"X-API-Key": API_KEY}
        ), timeout=5) as r:
            bytes_read = len(r.read())
            ms2 = int((time.monotonic()-t0)*1000)
            log("image-access", r.status == 200, f"HTTP {r.status} bytes={bytes_read}", ms2)
    except Exception as ex:
        ms2 = int((time.monotonic()-t0)*1000)
        log("image-access", False, str(ex), ms2)

# 4. 删除 note（清理）
code, data, ms = req("DELETE", f"/api/research-notes/{note_id}?session_id={SESSION}&user_id={UID}")
log("note-delete", code in (200, 204), f"HTTP {code}", ms)

print()
print("=== 汇总 ===")
passes = sum(1 for _, r, _ in results if r == "PASS")
fails  = sum(1 for _, r, _ in results if r == "FAIL")
print(f"PASS: {passes}  FAIL: {fails}")
