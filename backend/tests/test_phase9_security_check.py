from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "phase9_security_check.py"


def run_check(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_security_check_returns_failure_for_blocking_config(tmp_path):
    result = run_check(tmp_path)

    assert result.returncode == 1
    assert "BLOCKING: 2" in result.stdout


def test_security_check_returns_success_without_blockers(tmp_path):
    (tmp_path / ".env.server").write_text(
        "\n".join([
            "JWT_SECRET=0123456789abcdef0123456789abcdef",
            "API_AUTH_KEYS=local-test-key",
            "CORS_ALLOW_ORIGINS=https://finsight.example.invalid",
        ]),
        encoding="utf-8",
    )

    result = run_check(tmp_path)

    assert result.returncode == 0
    assert "BLOCKING: 0" in result.stdout


def test_security_check_rejects_dev_mode_on(tmp_path):
    (tmp_path / ".env.server").write_text(
        "\n".join([
            "DEV_MODE=on",
            "JWT_SECRET=0123456789abcdef0123456789abcdef",
            "API_AUTH_KEYS=local-test-key",
            "CORS_ALLOW_ORIGINS=https://finsight.example.invalid",
        ]),
        encoding="utf-8",
    )

    result = run_check(tmp_path)

    assert result.returncode == 1
    assert "DEV_MODE [BLOCKING]" in result.stdout


def test_security_check_parses_inline_comments_like_runtime(tmp_path):
    (tmp_path / ".env.server").write_text(
        "\n".join([
            "DEV_MODE=on # must not hide enabled dev mode",
            "JWT_SECRET=0123456789abcdef0123456789abcdef",
            "API_AUTH_KEYS=local-test-key",
            "CORS_ALLOW_ORIGINS=* # must not hide wildcard",
        ]),
        encoding="utf-8",
    )

    result = run_check(tmp_path)

    assert result.returncode == 1
    assert "DEV_MODE [BLOCKING]" in result.stdout
    assert "CORS_ALLOW_ORIGINS [BLOCKING]" in result.stdout
    assert "BLOCKING: 2" in result.stdout


def test_security_check_rejects_repository_example_placeholders(tmp_path):
    (tmp_path / ".env.server").write_text(
        "\n".join([
            "JWT_SECRET=REPLACE_ME_LONG_RANDOM_SECRET",
            "API_AUTH_KEYS=REPLACE_ME_INTERNAL_API_KEY",
        ]),
        encoding="utf-8",
    )

    result = run_check(tmp_path)

    assert result.returncode == 1
    assert "BLOCKING: 2" in result.stdout


def test_security_check_rejects_short_api_auth_key(tmp_path):
    (tmp_path / ".env.server").write_text(
        "\n".join([
            "JWT_SECRET=0123456789abcdef0123456789abcdef",
            "API_AUTH_KEYS=x",
        ]),
        encoding="utf-8",
    )

    result = run_check(tmp_path)

    assert result.returncode == 1
    assert "最短 key 长度 1" in result.stdout


def test_security_check_rejects_wildcard_in_cors_origin_list(tmp_path):
    (tmp_path / ".env.server").write_text(
        "\n".join([
            "JWT_SECRET=0123456789abcdef0123456789abcdef",
            "API_AUTH_KEYS=local-test-key",
            "CORS_ALLOW_ORIGINS=https://trusted.example.invalid,*",
        ]),
        encoding="utf-8",
    )

    result = run_check(tmp_path)

    assert result.returncode == 1
    assert "CORS_ALLOW_ORIGINS [BLOCKING]" in result.stdout


@pytest.mark.parametrize("cors_regex", ["^.*$", "https?://.*"])
def test_security_check_rejects_match_all_cors_origin_regex(tmp_path, cors_regex):
    (tmp_path / ".env.server").write_text(
        "\n".join([
            "JWT_SECRET=0123456789abcdef0123456789abcdef",
            "API_AUTH_KEYS=local-test-key",
            "CORS_ALLOW_ORIGINS=https://trusted.example.invalid",
            f"CORS_ALLOW_ORIGIN_REGEX={cors_regex}",
        ]),
        encoding="utf-8",
    )

    result = run_check(tmp_path)

    assert result.returncode == 1
    assert "CORS_ALLOW_ORIGIN_REGEX [BLOCKING]" in result.stdout


def test_security_check_rejects_invalid_cors_origin_regex(tmp_path):
    (tmp_path / ".env.server").write_text(
        "\n".join([
            "JWT_SECRET=0123456789abcdef0123456789abcdef",
            "API_AUTH_KEYS=local-test-key",
            "CORS_ALLOW_ORIGINS=https://trusted.example.invalid",
            "CORS_ALLOW_ORIGIN_REGEX=[",
        ]),
        encoding="utf-8",
    )

    result = run_check(tmp_path)

    assert result.returncode == 1
    assert "CORS_ALLOW_ORIGIN_REGEX [BLOCKING]" in result.stdout


def test_security_check_rejects_one_short_key_in_api_key_list(tmp_path):
    (tmp_path / ".env.server").write_text(
        "\n".join([
            "JWT_SECRET=0123456789abcdef0123456789abcdef",
            "API_AUTH_KEYS=x,local-test-key",
        ]),
        encoding="utf-8",
    )

    result = run_check(tmp_path)

    assert result.returncode == 1
    assert "最短 key 长度 1" in result.stdout


def test_security_check_rejects_placeholder_in_api_key_list(tmp_path):
    (tmp_path / ".env.server").write_text(
        "\n".join([
            "JWT_SECRET=0123456789abcdef0123456789abcdef",
            "API_AUTH_KEYS=local-test-key,REPLACE_ME_INTERNAL_API_KEY",
        ]),
        encoding="utf-8",
    )

    result = run_check(tmp_path)

    assert result.returncode == 1
    assert "API_AUTH_KEYS [BLOCKING]" in result.stdout
