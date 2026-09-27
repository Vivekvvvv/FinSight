# -*- coding: utf-8 -*-
"""phase9_llm_smoke 的后端聊天探针必须打真实路由：/chat/supervisor +
ChatRequest.query + 服务端 session——此前打 /api/chat:8766 且 body 用
message/硬编码 uid，路径、端口、字段、身份四重错，chat-endpoint 恒 FAIL。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "phase9_llm_smoke.py"


def _run_smoke_with_fake_backend(tmp_path: Path) -> tuple[subprocess.CompletedProcess[str], list[dict]]:
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
    calls.append({{"url": url, "data": (data or b"").decode("utf-8", "replace")}})
    if url.endswith("/api/me"):
        return Response(json.dumps({{"user_id": "api_x", "session_id": "sess:1"}}).encode())
    if url.endswith("/chat/supervisor"):
        return Response(json.dumps({{"response": "READY"}}).encode())
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


def test_llm_smoke_chat_probe_uses_real_supervisor_route(tmp_path):
    """探针必须先取 /api/me 的 session_id 再 POST /chat/supervisor(query+session_id)。
    修复前：打 :8766/api/chat、body 是 message 字段——四重错必 FAIL。"""
    result, calls = _run_smoke_with_fake_backend(tmp_path)

    assert "[PASS] chat-endpoint" in result.stdout, result.stdout[-600:]
    urls = [call["url"] for call in calls]
    assert any(url.endswith("/api/me") for url in urls), urls
    assert any(url.endswith("/chat/supervisor") for url in urls), urls
    assert not any("/api/chat" in url for url in urls), urls

    chat_calls = [call for call in calls if call["url"].endswith("/chat/supervisor")]
    body = json.loads(chat_calls[0]["data"])
    assert body["query"] == "Reply with exactly one word: READY"
    # session_id 必须来自 /api/me 下发值（require_matching_identity 校验基准），
    # 不是脚本内硬编码的 uid 拼出来的 private: 串
    assert body["session_id"] == "sess:1"


def test_llm_smoke_chat_probe_reports_fail_when_me_unavailable(tmp_path):
    """/api/me 挂掉时 chat-endpoint 必须 FAIL 而非静默跳过——假成功比失败更糟。"""
    runner = f'''
import io
import json
import runpy
import urllib.error
import urllib.request

urllib.request.urlopen = lambda request, **kw: (_ for _ in ()).throw(
    urllib.error.HTTPError(getattr(request, "full_url", "?"), 500, "boom", {{}}, io.BytesIO(b"{{}}"))
)
try:
    runpy.run_path({str(SCRIPT)!r}, run_name="__main__")
except SystemExit:
    pass
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

    assert "[FAIL] chat-endpoint" in result.stdout
