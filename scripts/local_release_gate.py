from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SECRET_PATTERNS = [
    re.compile(r"(?<![A-Za-z0-9_-])sk-(?!test-|primary-|backup-|a-|b-|very-secret-|secret-example-|x{8,})[A-Za-z0-9_-]{16,}"),
    re.compile(r"(?im)^\s*(JWT_SECRET|API_AUTH_KEYS)\s*=\s*(?!change-me|example|your-|placeholder|dummy)['\"]?[A-Za-z0-9_.:/+-]{24,}"),
]
SCAN_SUFFIXES = {".py", ".ts", ".vue", ".md", ".yml", ".yaml", ".json", ".toml", ".txt"}
SKIP_PARTS = {
    ".git",
    ".venv",
    "node_modules",
    "dist",
    "test-results",
    "playwright-report",
    "__pycache__",
    ".pytest_cache",
    "data",
    "logs",
    "archive",
}


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
        ["git", "ls-files"],
        cwd=str(ROOT),
        shell=False,
        text=True,
        encoding="utf-8",
        errors="ignore",
        capture_output=True,
    )
    if completed.returncode != 0:
        print("Cannot list tracked files; falling back to empty scan set.")
        return []
    return [ROOT / item for item in completed.stdout.splitlines() if item.strip()]


def scan_secrets() -> int:
    print("\n$ secret-scan")
    failures: list[str] = []
    for path in tracked_files():
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if any(part in SKIP_PARTS for part in relative.parts):
            continue
        if path.name in {".env", ".env.server", "user_config.json"}:
            failures.append(f"{relative}: local config file must not be committed")
            continue
        if path.suffix.lower() not in SCAN_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
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
