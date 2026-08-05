from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts import local_release_gate


def test_secret_scan_fails_closed_when_git_file_listing_fails(monkeypatch, capsys):
    monkeypatch.setattr(
        local_release_gate.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stdout=""),
    )

    result = local_release_gate.scan_secrets()

    assert result == 1
    output = capsys.readouterr().out
    assert "Secret scan failed" in output
    assert "Secret scan passed" not in output


def test_file_listing_includes_untracked_nonignored_files(monkeypatch):
    captured: list[str] = []

    def fake_run(command, **_kwargs):
        captured.extend(command)
        return SimpleNamespace(returncode=0, stdout="backend/app.py\0backend/new.py\0")

    monkeypatch.setattr(local_release_gate.subprocess, "run", fake_run)

    paths = local_release_gate.tracked_files()

    assert captured == ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"]
    assert [path.name for path in paths] == ["app.py", "new.py"]


def test_file_listing_preserves_non_ascii_paths(monkeypatch):
    def fake_run(_command, **_kwargs):
        return SimpleNamespace(returncode=0, stdout="docs/配置.py\0")

    monkeypatch.setattr(local_release_gate.subprocess, "run", fake_run)

    paths = local_release_gate.tracked_files()

    assert paths == [local_release_gate.ROOT / "docs" / "配置.py"]


@pytest.mark.parametrize("filename", [".env.production", ".ENV.PRODUCTION"])
def test_secret_scan_rejects_environment_variants(monkeypatch, tmp_path, capsys, filename):
    env_file = tmp_path / filename
    env_file.write_text("SAFE_LOOKING_VALUE=still-local-config\n", encoding="utf-8")
    monkeypatch.setattr(local_release_gate, "ROOT", tmp_path)
    monkeypatch.setattr(local_release_gate, "tracked_files", lambda: [env_file])

    result = local_release_gate.scan_secrets()

    assert result == 1
    assert f"{filename}: local config file must not be committed" in capsys.readouterr().out


def test_secret_scan_rejects_environment_file_inside_skipped_data_dir(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    env_file = data_dir / ".env.production"
    env_file.write_text("TOKEN=value\n", encoding="utf-8")
    monkeypatch.setattr(local_release_gate, "ROOT", tmp_path)
    monkeypatch.setattr(local_release_gate, "tracked_files", lambda: [env_file])

    assert local_release_gate.scan_secrets() == 1


def test_secret_scan_checks_example_environment_contents(monkeypatch, tmp_path):
    env_file = tmp_path / ".env.example"
    env_file.write_text("TOKEN=" + "ghp_" + "H" * 36 + "\n", encoding="utf-8")
    monkeypatch.setattr(local_release_gate, "ROOT", tmp_path)
    monkeypatch.setattr(local_release_gate, "tracked_files", lambda: [env_file])

    assert local_release_gate.scan_secrets() == 1


def test_secret_scan_checks_example_environment_inside_skipped_data_dir(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    env_file = data_dir / ".env.example"
    env_file.write_text("TOKEN=" + "ghp_" + "I" * 36 + "\n", encoding="utf-8")
    monkeypatch.setattr(local_release_gate, "ROOT", tmp_path)
    monkeypatch.setattr(local_release_gate, "tracked_files", lambda: [env_file])

    assert local_release_gate.scan_secrets() == 1


@pytest.mark.parametrize(
    "secret",
    [
        "ghp_" + "A" * 36,
        "github_pat_" + "B" * 30,
        "npm_" + "N" * 36,
        "AKIA" + "C" * 16,
    ],
)
def test_secret_scan_rejects_common_provider_credentials(monkeypatch, tmp_path, secret):
    source = tmp_path / "settings.py"
    source.write_text(f'TOKEN = "{secret}"\n', encoding="utf-8")
    monkeypatch.setattr(local_release_gate, "ROOT", tmp_path)
    monkeypatch.setattr(local_release_gate, "tracked_files", lambda: [source])

    assert local_release_gate.scan_secrets() == 1


@pytest.mark.parametrize("prefix", ["primary", "backup", "a", "b"])
def test_secret_scan_does_not_exempt_openai_style_key_prefixes(monkeypatch, tmp_path, prefix):
    source = tmp_path / "settings.py"
    source.write_text(f'TOKEN = "sk-{prefix}-{"Z" * 24}"\n', encoding="utf-8")
    monkeypatch.setattr(local_release_gate, "ROOT", tmp_path)
    monkeypatch.setattr(local_release_gate, "tracked_files", lambda: [source])

    assert local_release_gate.scan_secrets() == 1


def test_secret_scan_checks_shell_scripts(monkeypatch, tmp_path):
    script = tmp_path / "deploy.ps1"
    script.write_text('$token = "' + "ghp_" + "D" * 36 + '"\n', encoding="utf-8")
    monkeypatch.setattr(local_release_gate, "ROOT", tmp_path)
    monkeypatch.setattr(local_release_gate, "tracked_files", lambda: [script])

    assert local_release_gate.scan_secrets() == 1


def test_secret_scan_checks_archived_documents(monkeypatch, tmp_path):
    archive = tmp_path / "docs" / "archive"
    archive.mkdir(parents=True)
    document = archive / "old-runbook.md"
    document.write_text("TOKEN=" + "github_pat_" + "E" * 30, encoding="utf-8")
    monkeypatch.setattr(local_release_gate, "ROOT", tmp_path)
    monkeypatch.setattr(local_release_gate, "tracked_files", lambda: [document])

    assert local_release_gate.scan_secrets() == 1


def test_secret_scan_checks_nested_source_data_directory(monkeypatch, tmp_path):
    source_dir = tmp_path / "frontend" / "src" / "data"
    source_dir.mkdir(parents=True)
    source = source_dir / "config.ts"
    source.write_text('const token = "' + "ghp_" + "F" * 36 + '";', encoding="utf-8")
    monkeypatch.setattr(local_release_gate, "ROOT", tmp_path)
    monkeypatch.setattr(local_release_gate, "tracked_files", lambda: [source])

    assert local_release_gate.scan_secrets() == 1


@pytest.mark.parametrize("key_type", ["", "ENCRYPTED ", "DSA "])
def test_secret_scan_rejects_private_key_material(monkeypatch, tmp_path, key_type):
    key_file = tmp_path / "deploy-key.txt"
    key_file.write_text("-----BEGIN " + key_type + "PRIVATE KEY-----\n", encoding="utf-8")
    monkeypatch.setattr(local_release_gate, "ROOT", tmp_path)
    monkeypatch.setattr(local_release_gate, "tracked_files", lambda: [key_file])

    assert local_release_gate.scan_secrets() == 1


@pytest.mark.parametrize("filename", ["deploy.pem", "deploy.key", "Dockerfile"])
def test_secret_scan_checks_deployment_key_files(monkeypatch, tmp_path, filename):
    key_file = tmp_path / filename
    key_file.write_text("-----BEGIN " + "PRIVATE KEY-----\n", encoding="utf-8")
    monkeypatch.setattr(local_release_gate, "ROOT", tmp_path)
    monkeypatch.setattr(local_release_gate, "tracked_files", lambda: [key_file])

    assert local_release_gate.scan_secrets() == 1


def test_secret_scan_checks_javascript_config(monkeypatch, tmp_path):
    config = tmp_path / "vite.config.mjs"
    config.write_text('export const token = "' + "github_pat_" + "G" * 30 + '";', encoding="utf-8")
    monkeypatch.setattr(local_release_gate, "ROOT", tmp_path)
    monkeypatch.setattr(local_release_gate, "tracked_files", lambda: [config])

    assert local_release_gate.scan_secrets() == 1


@pytest.mark.parametrize("filename", [".npmrc", ".NPMRC"])
def test_secret_scan_checks_npm_config(monkeypatch, tmp_path, filename):
    config = tmp_path / filename
    config.write_text("//registry.npmjs.org/:_authToken=" + "npm_" + "P" * 36, encoding="utf-8")
    monkeypatch.setattr(local_release_gate, "ROOT", tmp_path)
    monkeypatch.setattr(local_release_gate, "tracked_files", lambda: [config])

    assert local_release_gate.scan_secrets() == 1


def test_secret_scan_fails_closed_when_file_cannot_be_read(monkeypatch, tmp_path, capsys):
    source = tmp_path / "settings.py"
    source.write_text("SAFE = True\n", encoding="utf-8")
    monkeypatch.setattr(local_release_gate, "ROOT", tmp_path)
    monkeypatch.setattr(local_release_gate, "tracked_files", lambda: [source])

    original_read_text = local_release_gate.Path.read_text

    def fail_for_source(path, *args, **kwargs):
        if path == source:
            raise PermissionError("private path details")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(local_release_gate.Path, "read_text", fail_for_source)

    assert local_release_gate.scan_secrets() == 1
    output = capsys.readouterr().out
    assert "settings.py: cannot read file (PermissionError)" in output
    assert "private path details" not in output
