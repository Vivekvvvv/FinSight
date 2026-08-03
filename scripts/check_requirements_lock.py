#!/usr/bin/env python3
"""Fail when requirements.txt contains unpinned direct requirements."""

from __future__ import annotations

from pathlib import Path
import sys


def _strip_inline_comment(line: str) -> str:
    for index, char in enumerate(line):
        if char == "#" and index > 0 and line[index - 1].isspace():
            return line[:index].rstrip()
    return line


def _requirements(path: Path) -> dict[str, str]:
    items: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = _strip_inline_comment(raw.strip())
        if not line or line.startswith("#") or line.startswith(("-r ", "--")):
            continue
        if "==" not in line:
            continue
        name, version = line.split("==", 1)
        name = name.split("[", 1)[0].strip().lower()
        items[name] = version.strip()
    return items


def main() -> int:
    path = Path("requirements.txt")
    bad: list[str] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("-r ", "--", "git+", "http://", "https://")):
            continue
        if "==" not in line:
            bad.append(f"{line_no}: {line}")
    if bad:
        print("requirements.txt must contain only pinned requirements:")
        print("\n".join(bad))
        return 1
    source = _requirements(Path("requirements.in"))
    locked = _requirements(path)
    drift = [
        f"{name}: requirements.in=={version}, requirements.txt=={locked.get(name) or 'MISSING'}"
        for name, version in sorted(source.items())
        if locked.get(name) != version
    ]
    if drift:
        print("requirements.in and requirements.txt direct pins are out of sync:")
        print("\n".join(drift))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
