from __future__ import annotations

from pathlib import Path
import subprocess
import sys


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "phase9_notes_smoke.py"


def test_notes_smoke_returns_failure_when_upload_probe_fails(tmp_path):
    runner = f'''
import json
import os
import runpy
import urllib.error
import urllib.request

os.environ["API_AUTH_SMOKE_KEY"] = "local-test-key"

class Response:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()

def fake_urlopen(request, **_kwargs):
    if request.method == "POST" and request.full_url.endswith("/api/research-notes"):
        return Response({{"note_id": "note-1"}})
    if request.method == "POST" and "/images" in request.full_url:
        raise urllib.error.HTTPError(request.full_url, 500, "failed", {{}}, None)
    return Response({{}})

urllib.request.urlopen = fake_urlopen
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
    assert "image-upload" in result.stdout
