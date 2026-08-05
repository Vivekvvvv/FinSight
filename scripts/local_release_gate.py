from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SECRET_PATTERNS = [
    re.compile(r"(?<![A-Za-z0-9_-])sk-(?!test-|very-secret-|secret-example-|x{8,})[A-Za-z0-9_-]{16,}"),
    re.compile(r"(?<![A-Za-z0-9_])gh[pousr]_[A-Za-z0-9]{36,}"),
    re.compile(r"(?<![A-Za-z0-9_])github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"(?<![A-Za-z0-9_])npm_[A-Za-z0-9]{36,}"),
    re.compile(r"(?<![A-Z0-9])AKIA[0-9A-Z]{16}(?![A-Z0-9])"),
    re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"),
    re.compile(r"(?im)^\s*(JWT_SECRET|API_AUTH_KEYS)\s*=\s*(?!change-me|example|your-|placeholder|dummy|replace_me|smoke_placeholder)['\"]?[A-Za-z0-9_.:/+-]{24,}"),
]
SCAN_SUFFIXES = {
    ".cfg",
    ".cmd",
    ".conf",
    ".css",
    ".html",
    ".ini",
    ".js",
    ".jsx",
    ".json",
    ".key",
    ".md",
    ".mjs",
    ".cjs",
    ".ps1",
    ".pem",
    ".py",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".vue",
    ".yaml",
    ".yml",
}
SCAN_FILENAMES = {".npmrc", "dockerfile", "makefile", "procfile"}
SKIP_PARTS = {
    ".git",
    ".venv",
    "node_modules",
    "dist",
    "test-results",
    "playwright-report",
    "__pycache__",
    ".pytest_cache",
}
TOP_LEVEL_SKIP_DIRS = {"data", "logs"}


def run(cmd: list[str], cwd: Path = ROOT) -> int:
    print(f"\n$ {' '.join(cmd)}")
    executable = cmd[0]
    if executable == "npm":
        cmd = ["cmd", "/c", *cmd]
    completed = subprocess.run(cmd, cwd=str(cwd), shell=False)
    return completed.returncode


def python_executable() -> str:
    candidates = [
        ROOT / ".venv" / "Scripts" / "python.exe",
        ROOT / "venv" / "Scripts" / "python.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return sys.executable


def tracked_files() -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=str(ROOT),
        shell=False,
        text=True,
        encoding="utf-8",
        errors="ignore",
        capture_output=True,
    )
    if completed.returncode != 0:
        raise RuntimeError("cannot list tracked files")
    return [ROOT / item for item in completed.stdout.split("\0") if item]


def scan_secrets() -> int:
    print("\n$ secret-scan")
    failures: list[str] = []
    try:
        paths = tracked_files()
    except RuntimeError as exc:
        print(f"Secret scan failed: {exc}")
        return 1
    for path in paths:
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        normalized_name = path.name.lower()
        is_env_file = normalized_name.startswith(".env")
        is_local_env = is_env_file and not normalized_name.endswith(".example")
        if is_local_env or normalized_name == "user_config.json":
            failures.append(f"{relative}: local config file must not be committed")
            continue
        if (
            any(part in SKIP_PARTS for part in relative.parts)
            or relative.parts[0] in TOP_LEVEL_SKIP_DIRS
        ) and not is_env_file:
            continue
        if not is_env_file and path.suffix.lower() not in SCAN_SUFFIXES and normalized_name not in SCAN_FILENAMES:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            failures.append(f"{relative}: cannot read file ({type(exc).__name__})")
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                failures.append(f"{relative}: possible secret matched {pattern.pattern}")
                break
    if failures:
        print("Secret scan failed:")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("Secret scan passed.")
    return 0


def main() -> int:
    commands = [
        [python_executable(), "-m", "pytest", "backend/tests/test_demo_mode.py", "backend/tests/test_market_evidence.py", "backend/tests/test_next_actions.py", "-q"],
        ["npm", "run", "typecheck"],
        ["npm", "run", "build"],
        ["git", "diff", "--check"],
        ["git", "status", "--short"],
    ]
    exit_code = scan_secrets()
    for cmd in commands:
        cwd = ROOT / "frontend-vue" if cmd[0] == "npm" else ROOT
        exit_code = run(cmd, cwd=cwd) or exit_code
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
