"""Phase 8 smoke: image upload via proper multipart"""
import sys, io, urllib.request, json

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = "http://localhost:18080"
SESSION = "public:anonymous:phase8-smoke"
USER = "default_user"
NOTE_ID = "note_4e93c6c27a97"

# Minimal valid 1x1 PNG (67 bytes)
PNG = bytes([
    0x89,0x50,0x4E,0x47,0x0D,0x0A,0x1A,0x0A,  # signature
    0x00,0x00,0x00,0x0D,0x49,0x48,0x44,0x52,  # IHDR length + type
    0x00,0x00,0x00,0x01,0x00,0x00,0x00,0x01,  # 1x1
    0x08,0x02,0x00,0x00,0x00,0x90,0x77,0x53,  # 8-bit RGB, CRC
    0xDE,0x00,0x00,0x00,0x0C,0x49,0x44,0x41,  # IDAT
    0x54,0x08,0xD7,0x63,0xF8,0xCF,0xC0,0x00,  # compressed 1px red
    0x00,0x00,0x02,0x00,0x01,0xE2,0x21,0xBC,  # IDAT CRC
    0x33,0x00,0x00,0x00,0x00,0x49,0x45,0x4E,  # IEND
    0x44,0xAE,0x42,0x60,0x82              # IEND CRC
])

BOUNDARY = b"PhaseSmokeUpload8"
CRLF = b"\r\n"

body = (
    b"--" + BOUNDARY + CRLF
    + b'Content-Disposition: form-data; name="file"; filename="smoke.png"' + CRLF
    + b"Content-Type: image/png" + CRLF
    + CRLF
    + PNG + CRLF
    + b"--" + BOUNDARY + b"--" + CRLF
)

url = f"{BASE}/api/research-notes/{NOTE_ID}/images?session_id={SESSION}&user_id={USER}"
req = urllib.request.Request(
    url, data=body, method="POST",
    headers={"Content-Type": f"multipart/form-data; boundary={BOUNDARY.decode()}"}
)

try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read())
        print(f"UPLOAD OK: {json.dumps(result)}")
        image_url = result.get("url") or result.get("image_url") or result.get("path")
        print(f"  image_url={image_url}")

        if image_url:
            # Verify access
            access_url = BASE + image_url if image_url.startswith("/") else image_url
            req2 = urllib.request.Request(access_url)
            with urllib.request.urlopen(req2, timeout=10) as r2:
                data = r2.read()
                print(f"  GET image -> {r2.status}, bytes={len(data)}")
        print("UPLOAD_SMOKE: PASS")
except urllib.error.HTTPError as e:
    body_err = e.read().decode(errors="replace")
    print(f"UPLOAD FAIL {e.code}: {body_err}")
    print("UPLOAD_SMOKE: FAIL")
except Exception as ex:
    print(f"UPLOAD ERROR: {ex}")
    print("UPLOAD_SMOKE: FAIL")
