from __future__ import annotations

from pathlib import Path
import subprocess
import sys


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "phase9_auth_smoke.py"


def run_with_fake_backend(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    runner = f'''
import json
import runpy
import urllib.request

class Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps({{"user_id": "guest:anonymous"}}).encode()

urllib.request.urlopen = lambda *_args, **_kwargs: Response()
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


def test_auth_smoke_returns_failure_when_blocker_is_reported(tmp_path):
    result = run_with_fake_backend(tmp_path)

    assert result.returncode == 1
    assert "BLOCKING:" in result.stdout
    assert "jwt-secret-exists" in result.stdout


def test_auth_smoke_rejects_dev_mode_on_with_inline_comment(tmp_path):
    (tmp_path / ".env.server").write_text(
        "\n".join([
            "DEV_MODE=on # must match runtime parsing",
            "JWT_SECRET=0123456789abcdef0123456789abcdef",
        ]),
        encoding="utf-8",
    )

    result = run_with_fake_backend(tmp_path)

    assert result.returncode == 1
    assert "dev-mode-off" in result.stdout
    assert "BLOCKING:" in result.stdout


def test_auth_smoke_rejects_repository_placeholders(tmp_path):
    (tmp_path / ".env.server").write_text(
        "\n".join([
            "JWT_SECRET=REPLACE_ME_LONG_RANDOM_SECRET",
            "API_AUTH_KEYS=REPLACE_ME_INTERNAL_API_KEY",
        ]),
        encoding="utf-8",
    )

    result = run_with_fake_backend(tmp_path)

    assert result.returncode == 1
    assert "JWT_SECRET:    MISSING" in result.stdout
    assert "API_AUTH_KEYS: MISSING" in result.stdout


def test_auth_smoke_rejects_short_api_key(tmp_path):
    (tmp_path / ".env.server").write_text(
        "\n".join([
            "JWT_SECRET=0123456789abcdef0123456789abcdef",
            "API_AUTH_KEYS=x",
        ]),
        encoding="utf-8",
    )

    result = run_with_fake_backend(tmp_path)

    assert result.returncode == 1
    assert "API_AUTH_KEYS: MISSING" in result.stdout


def test_auth_smoke_uses_last_duplicate_environment_value(tmp_path):
    (tmp_path / ".env.server").write_text(
        "\n".join([
            "DEV_MODE=false",
            "DEV_MODE=on",
            "JWT_SECRET=0123456789abcdef0123456789abcdef",
        ]),
        encoding="utf-8",
    )

    result = run_with_fake_backend(tmp_path)

    assert result.returncode == 1
    assert "dev-mode-off" in result.stdout


def test_auth_smoke_fails_when_identity_response_is_not_json(tmp_path):
    runner = f'''
import runpy
import urllib.request

class Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return b"not-json"

urllib.request.urlopen = lambda *_args, **_kwargs: Response()
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
    assert "[FAIL] no-dev-bypass" in result.stdout


def test_auth_smoke_fails_when_valid_key_identity_is_not_json(tmp_path):
    (tmp_path / ".env.server").write_text(
        "\n".join([
            "JWT_SECRET=0123456789abcdef0123456789abcdef",
            "API_AUTH_KEYS=local-test-key",
        ]),
        encoding="utf-8",
    )
    runner = f'''
import io
import runpy
import urllib.error
import urllib.request

class Response:
    status = 200

    def __init__(self, body=b"{{}}"):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body

def fake_urlopen(request, **_kwargs):
    url = request if isinstance(request, str) else request.full_url
    if url.endswith("/api/health"):
        return Response()
    headers = {{}} if isinstance(request, str) else dict(request.header_items())
    if headers.get("X-api-key") == "local-test-key":
        return Response(b"not-json")
    raise urllib.error.HTTPError(url, 401, "unauthorized", {{}}, io.BytesIO(b"{{}}"))

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
    assert "[FAIL] me-valid-key-payload" in result.stdout
