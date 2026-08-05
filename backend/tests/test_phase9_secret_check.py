from __future__ import annotations

from pathlib import Path
import subprocess
import sys


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "phase9_secret_check.py"


def test_secret_check_missing_env_is_a_clean_failure(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert result.returncode == 1
    assert ".env.server 不存在" in result.stdout
    assert "BLOCKING: JWT_SECRET" in result.stdout
    assert "Traceback" not in result.stderr


def test_secret_check_returns_success_for_complete_minimum_config(tmp_path):
    (tmp_path / ".env.server").write_text(
        "\n".join([
            "JWT_SECRET=0123456789abcdef0123456789abcdef",
            "API_AUTH_KEYS=local-test-key",
            "OPENAI_API_KEY=local-test-llm-key",
        ]),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert result.returncode == 0
    assert "无阻塞项" in result.stdout


def test_secret_check_rejects_repository_example_placeholders(tmp_path):
    (tmp_path / ".env.server").write_text(
        "\n".join([
            "JWT_SECRET=REPLACE_ME_LONG_RANDOM_SECRET",
            "API_AUTH_KEYS=REPLACE_ME_INTERNAL_API_KEY",
            "OPENAI_API_KEY=local-test-llm-key",
        ]),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert result.returncode == 1
    assert result.stdout.count("EMPTY/PLACEHOLDER") >= 2


def test_secret_check_rejects_repository_llm_key_placeholder(tmp_path):
    (tmp_path / ".env.server").write_text(
        "\n".join([
            "JWT_SECRET=0123456789abcdef0123456789abcdef",
            "API_AUTH_KEYS=local-test-key",
            "OPENAI_COMPATIBLE_API_KEY=sk-REPLACE_ME",
        ]),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert result.returncode == 1
    assert "OPENAI_COMPATIBLE_API_KEY" in result.stdout
    assert "EMPTY/PLACEHOLDER" in result.stdout


def test_secret_check_rejects_short_security_keys(tmp_path):
    (tmp_path / ".env.server").write_text(
        "\n".join([
            "JWT_SECRET=too-short",
            "API_AUTH_KEYS=x",
            "OPENAI_API_KEY=local-test-llm-key",
        ]),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert result.returncode == 1
    assert result.stdout.count("PRESENT_BUT_SHORT") == 2
    assert "BLOCKING: JWT_SECRET" in result.stdout
    assert "BLOCKING: API_AUTH_KEYS" in result.stdout


def test_secret_check_does_not_count_inline_comment_as_secret_length(tmp_path):
    (tmp_path / ".env.server").write_text(
        "\n".join([
            "JWT_SECRET=short # this comment must not count toward length",
            "API_AUTH_KEYS=local-test-key",
            "OPENAI_API_KEY=local-test-llm-key",
        ]),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert result.returncode == 1
    assert "PRESENT_BUT_SHORT (len=5, need>=32)" in result.stdout
    assert "BLOCKING: JWT_SECRET" in result.stdout


def test_secret_check_rejects_one_short_key_in_api_key_list(tmp_path):
    (tmp_path / ".env.server").write_text(
        "\n".join([
            "JWT_SECRET=0123456789abcdef0123456789abcdef",
            "API_AUTH_KEYS=x,local-test-key",
            "OPENAI_API_KEY=local-test-llm-key",
        ]),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert result.returncode == 1
    assert "shortest_len=1" in result.stdout


def test_secret_check_rejects_placeholder_in_api_key_list(tmp_path):
    (tmp_path / ".env.server").write_text(
        "\n".join([
            "JWT_SECRET=0123456789abcdef0123456789abcdef",
            "API_AUTH_KEYS=local-test-key,REPLACE_ME_INTERNAL_API_KEY",
            "OPENAI_API_KEY=local-test-llm-key",
        ]),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert result.returncode == 1
    assert "API_AUTH_KEYS" in result.stdout
    assert "EMPTY/PLACEHOLDER" in result.stdout
