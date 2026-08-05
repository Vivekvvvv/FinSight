from __future__ import annotations

from pathlib import Path
import subprocess
import sys


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "phase9_llm_smoke.py"


def test_llm_smoke_returns_failure_when_chat_probe_fails(tmp_path):
    runner = f'''
import os
import runpy
import urllib.error
import urllib.request

os.environ["API_AUTH_SMOKE_KEY"] = "local-test-key"

def fail_chat(request, **_kwargs):
    raise urllib.error.HTTPError(request.full_url, 503, "unavailable", {{}}, None)

urllib.request.urlopen = fail_chat
runpy.run_path({str(SCRIPT)!r}, run_name="__main__")
'''
    result = subprocess.run(
        [sys.executable, "-c", runner],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert result.returncode == 1
    assert "FAIL: 1" in result.stdout
