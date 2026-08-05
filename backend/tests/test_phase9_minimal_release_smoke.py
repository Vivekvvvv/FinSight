from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "phase9_minimal_release_smoke.py"


def run_with_fake_services(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    runner = f'''
import json
import io
import runpy
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

class Process:
    pid = 1234

    def terminate(self):
        pass

    def wait(self, timeout=None):
        return 0

    def kill(self):
        pass

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
    url = request if isinstance(request, str) else request.full_url
    headers = {{}} if isinstance(request, str) else dict(request.header_items())
    if url.endswith("/api/me"):
        if "X-api-key" in headers:
            return Response({{"user_id": "api_123"}})
        raise urllib.error.HTTPError(url, 401, "unauthorized", {{}}, io.BytesIO(b"{{}}"))
    return Response({{}})

def fake_popen(*_args, **kwargs):
    Path({str(Path('captured-child-env.json'))!r}).write_text(
        json.dumps(kwargs.get("env", {{}})),
        encoding="utf-8",
    )
    return Process()

subprocess.run = lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stderr=b"")
subprocess.Popen = fake_popen
time.sleep = lambda *_args, **_kwargs: None
urllib.request.urlopen = fake_urlopen
runpy.run_path({str(SCRIPT)!r}, run_name="__main__")
'''
    return subprocess.run(
        [sys.executable, "-c", runner],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_minimal_release_smoke_returns_failure_for_reported_blockers(tmp_path):
    result = run_with_fake_services(tmp_path)

    assert result.returncode == 1
    assert "READY_WITH_BLOCKERS" in result.stdout
    assert "[PASS] no-dev-bypass" in result.stdout


def test_minimal_release_smoke_rejects_short_api_auth_key(tmp_path):
    (tmp_path / ".env.server").write_text(
        "\n".join([
            "JWT_SECRET=0123456789abcdef0123456789abcdef",
            "API_AUTH_KEYS=x",
        ]),
        encoding="utf-8",
    )

    result = run_with_fake_services(tmp_path)

    assert result.returncode == 1
    assert "B2-API_AUTH_KEYS" in result.stdout


def test_minimal_release_smoke_rejects_placeholder_in_api_key_list(tmp_path):
    (tmp_path / ".env.server").write_text(
        "\n".join([
            "JWT_SECRET=0123456789abcdef0123456789abcdef",
            "API_AUTH_KEYS=local-test-key,REPLACE_ME_INTERNAL_API_KEY",
        ]),
        encoding="utf-8",
    )

    result = run_with_fake_services(tmp_path)

    assert result.returncode == 1
    assert "B2-API_AUTH_KEYS" in result.stdout


def test_minimal_release_smoke_does_not_count_inline_comment_as_jwt_length(tmp_path):
    (tmp_path / ".env.server").write_text(
        "\n".join([
            "JWT_SECRET=short # this comment must not count toward length",
            "API_AUTH_KEYS=local-test-key",
        ]),
        encoding="utf-8",
    )

    result = run_with_fake_services(tmp_path)

    assert result.returncode == 1
    assert "B1-JWT_SECRET" in result.stdout


def test_minimal_release_smoke_rejects_enabled_dev_mode(tmp_path):
    (tmp_path / ".env.server").write_text(
        "\n".join([
            "DEV_MODE=on",
            "JWT_SECRET=0123456789abcdef0123456789abcdef",
            "API_AUTH_KEYS=local-test-key",
        ]),
        encoding="utf-8",
    )

    result = run_with_fake_services(tmp_path)

    assert result.returncode == 1
    assert "B0-DEV_MODE" in result.stdout


def test_minimal_release_smoke_passes_server_env_to_backend_process(tmp_path):
    (tmp_path / ".env.server").write_text(
        "\n".join([
            "POSTGRES_DB=finsight",
            "POSTGRES_USER=finsight_user",
            "POSTGRES_PASSWORD=local-test-password",
        ]),
        encoding="utf-8",
    )

    run_with_fake_services(tmp_path)

    captured = json.loads((tmp_path / "captured-child-env.json").read_text(encoding="utf-8"))
    assert captured["POSTGRES_DB"] == "finsight"
    assert captured["POSTGRES_USER"] == "finsight_user"
    assert captured["POSTGRES_PASSWORD"] == "local-test-password"


def test_minimal_release_smoke_rejects_repository_llm_key_placeholder(tmp_path):
    (tmp_path / ".env.server").write_text(
        "\n".join([
            "JWT_SECRET=0123456789abcdef0123456789abcdef",
            "API_AUTH_KEYS=local-test-key",
            "OPENAI_COMPATIBLE_API_KEY=sk-REPLACE_ME",
            "OPENAI_COMPATIBLE_API_BASE=https://example.invalid/v1",
        ]),
        encoding="utf-8",
    )

    result = run_with_fake_services(tmp_path)

    assert result.returncode == 1
    assert "B3-LLM_KEY" in result.stdout
