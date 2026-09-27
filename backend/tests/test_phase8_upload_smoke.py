# -*- coding: utf-8 -*-
"""phase8_upload_smoke 上传失败必须以非 0 退出——与 phase8_llm_smoke
同款缺陷：except 只打印 UPLOAD_SMOKE:FAIL 就自然结束（rc=0），
门禁执行时把失败报成通过。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "phase8_upload_smoke.py"

RUNNER_HEAD = '''
import io
import json
import runpy
import urllib.error
import urllib.request
'''


def _run(tmp_path: Path, fake_urlopen_src: str) -> subprocess.CompletedProcess[str]:
    runner = RUNNER_HEAD + fake_urlopen_src + f'''
urllib.request.urlopen = fake_urlopen
try:
    runpy.run_path({str(SCRIPT)!r}, run_name="__main__")
except SystemExit as exc:
    code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    raise SystemExit(code)
'''
    return subprocess.run(
        [sys.executable, "-c", runner],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        env={**os.environ},
    )


def test_upload_smoke_exits_zero_on_success(tmp_path):
    result = _run(tmp_path, '''
def fake_urlopen(request, **kwargs):
    url = getattr(request, "full_url", "")
    class Resp:
        status = 200
        def __init__(self, body): self._body = body
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return self._body
    if "/images" in url and getattr(request, "data", None) is not None:
        return Resp(json.dumps({"url": "/api/research-notes/n1/images/f.png"}).encode())
    return Resp(b"PNG")
''')

    assert result.returncode == 0, result.stdout[-400:] + result.stderr[-400:]
    assert "UPLOAD_SMOKE: PASS" in result.stdout


def test_upload_smoke_exits_nonzero_on_http_error(tmp_path):
    result = _run(tmp_path, '''
def fake_urlopen(request, **kwargs):
    raise urllib.error.HTTPError("http://x", 404, "nf", {}, io.BytesIO(b"no note"))
''')

    assert result.returncode != 0
    assert "UPLOAD_SMOKE: FAIL" in result.stdout


def test_upload_smoke_exits_nonzero_on_connection_error(tmp_path):
    result = _run(tmp_path, '''
def fake_urlopen(request, **kwargs):
    raise urllib.error.URLError("connection refused")
''')

    assert result.returncode != 0
    assert "UPLOAD_SMOKE: FAIL" in result.stdout
