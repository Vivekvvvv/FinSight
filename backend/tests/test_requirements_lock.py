from __future__ import annotations

from pathlib import Path

from scripts.check_requirements_lock import _requirements, _strip_inline_comment


def _write_requirements(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_requirements_ignores_inline_comment_after_pin(tmp_path):
    path = _write_requirements(
        tmp_path / "requirements.txt",
        "package==1.2.3 # deployment note\n",
    )

    assert _requirements(path) == {"package": "1.2.3"}


def test_requirements_preserves_uncommented_pin(tmp_path):
    path = _write_requirements(tmp_path / "requirements.txt", "package==1.2.3\n")

    assert _requirements(path) == {"package": "1.2.3"}


def test_requirements_preserves_extras_and_marker(tmp_path):
    path = _write_requirements(
        tmp_path / "requirements.txt",
        'package[feature]==1.2.3; python_version >= "3.11"\n',
    )

    assert _requirements(path) == {
        "package": '1.2.3; python_version >= "3.11"',
    }


def test_inline_comment_parser_preserves_url_fragment():
    requirement = "https://example.test/package.whl#sha256=abc123"

    assert _strip_inline_comment(requirement) == requirement
