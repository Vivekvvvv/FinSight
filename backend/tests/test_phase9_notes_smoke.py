# -*- coding: utf-8 -*-
"""phase9_notes_smoke 必须打后端真实端口 8000 且用 /api/me 下发身份——
此前 BASE=localhost:8766（无服务）+ UID/SESSION 硬编码 api_292e...，
对任何健康后端全链路必挂。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "phase9_notes_smoke.py"


def _run_smoke(tmp_path: Path) -> tuple[subprocess.CompletedProcess[str], list[dict]]:
    runner = f'''
import io
import json
import runpy
import urllib.error
import urllib.request

calls = []

class Response:
    status = 200

    def __init__(self, body):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self._body


def fake_urlopen(request, **kwargs):
    url = request.full_url if hasattr(request, "full_url") else request
    data = getattr(request, "data", None)
    method = request.get_method() if hasattr(request, "get_method") else "GET"
    calls.append({{"url": url, "method": method,
                   "data": (data or b"").decode("utf-8", "replace")}})
    if method == "GET" and url.endswith("/api/me"):
        return Response(json.dumps({{"user_id": "api_x", "session_id": "sess:1"}}).encode())
    if method == "POST" and url.endswith("/api/research-notes"):
        return Response(json.dumps({{"note_id": "n1"}}).encode())
    if method == "POST" and "/images" in url:
        return Response(json.dumps({{"url": "/api/research-notes/n1/images/f.png"}}).encode())
    if method == "DELETE":
        return Response(b"{{}}")
    if method == "GET" and "images" in url:
        return Response(b"PNG")
    raise urllib.error.HTTPError(url, 404, "not found", {{}}, io.BytesIO(b"{{}}"))

urllib.request.urlopen = fake_urlopen
try:
    runpy.run_path({str(SCRIPT)!r}, run_name="__main__")
except SystemExit:
    pass
print("CALLS_JSON:" + json.dumps(calls))
'''
    result = subprocess.run(
        [sys.executable, "-c", runner],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        env={**os.environ, "API_AUTH_SMOKE_KEY": "local-test-key"},
    )
    calls: list[dict] = []
    for line in result.stdout.splitlines():
        if line.startswith("CALLS_JSON:"):
            calls = json.loads(line[len("CALLS_JSON:"):])
    return result, calls


def test_notes_smoke_uses_real_port_and_me_identity(tmp_path):
    result, calls = _run_smoke(tmp_path)

    assert "[PASS] me-identity" in result.stdout, result.stdout[-600:]
    assert "[PASS] note-create" in result.stdout, result.stdout[-600:]
    assert "[PASS] image-upload" in result.stdout, result.stdout[-600:]
    assert "[PASS] note-delete" in result.stdout, result.stdout[-600:]

    urls = [call["url"] for call in calls]
    # 后端真实端口 8000；8766 是旧死端口
    assert urls and all(url.startswith("http://localhost:8000") for url in urls), urls
    assert not any("8766" in url for url in urls), urls
    assert any(url.endswith("/api/me") for url in urls), urls

    create = next(c for c in calls if c["method"] == "POST" and c["url"].endswith("/api/research-notes"))
    body = json.loads(create["data"])
    assert body["user_id"] == "api_x"
    assert body["session_id"] == "sess:1"

    upload = next(c for c in calls if c["method"] == "POST" and "/images" in c["url"])
    assert "session_id=sess%3A1" in upload["url"] or "session_id=sess:1" in upload["url"]
    assert "user_id=api_x" in upload["url"]
