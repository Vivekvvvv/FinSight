from __future__ import annotations

from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version
import pytest

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


@pytest.mark.parametrize("filename", ["requirements.in", "requirements.txt"])
@pytest.mark.parametrize(
    "package", ["langgraph", "langgraph-checkpoint-sqlite", "langgraph-checkpoint-postgres"]
)
def test_langgraph_packages_accept_pinned_runtime_dependencies(filename, package):
    root = Path(__file__).resolve().parents[2]
    pins = _requirements(root / filename)
    assert metadata.version(package) == pins[package]
    for raw in metadata.requires(package) or []:
        requirement = Requirement(raw)
        if requirement.name in pins and (
            requirement.marker is None or requirement.marker.evaluate()
        ):
            version = Version(pins[requirement.name])
            assert version in requirement.specifier, (
                f"{filename}: {requirement.name}=={version} conflicts with {requirement}"
            )
