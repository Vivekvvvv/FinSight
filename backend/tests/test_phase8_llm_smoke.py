# -*- coding: utf-8 -*-
"""phase8_llm_smoke 的 LLM 调用失败必须以非 0 退出——此前 except 只打印
FAIL 就自然结束（rc=0），作为门禁运行时把坏掉的 LLM 报成通过。"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "phase8_llm_smoke.py"

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
        env={**os.environ, "OPENAI_COMPATIBLE_API_KEY": "local-test-key"},
    )


def test_llm_smoke_exits_zero_on_success(tmp_path):
    result = _run(tmp_path, '''
def fake_urlopen(request, **kwargs):
    class Resp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self):
            return json.dumps({"choices": [{"message": {"content": "SMOKE_OK"}}],
                               "usage": {"total_tokens": 7}}).encode()
    return Resp()
''')

    assert result.returncode == 0, result.stdout[-400:] + result.stderr[-400:]
    assert "LLM_SMOKE: PASS" in result.stdout


def test_llm_smoke_exits_nonzero_on_http_error(tmp_path):
    result = _run(tmp_path, '''
def fake_urlopen(request, **kwargs):
    raise urllib.error.HTTPError("http://x", 500, "boom", {}, io.BytesIO(b"bad"))
''')

    assert result.returncode != 0
    assert "LLM_SMOKE: FAIL" in result.stdout


def test_llm_smoke_exits_nonzero_on_connection_error(tmp_path):
    result = _run(tmp_path, '''
def fake_urlopen(request, **kwargs):
    raise urllib.error.URLError("connection refused")
''')

    assert result.returncode != 0
    assert "LLM_SMOKE: FAIL" in result.stdout


def test_llm_smoke_exits_nonzero_on_malformed_response(tmp_path):
    """返回体不是预期 choices 结构时也应 FAIL 退出——KeyError 走 except Exception。"""
    result = _run(tmp_path, '''
def fake_urlopen(request, **kwargs):
    class Resp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"{}"
    return Resp()
''')

    assert result.returncode != 0
    assert "LLM_SMOKE: FAIL" in result.stdout
