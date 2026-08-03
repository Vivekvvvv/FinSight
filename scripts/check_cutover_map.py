#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""静态校验当前默认架构是否为 Python + Vue。

文件名保留 `check_cutover_map.py` 是为了兼容旧命令入口；脚本语义已经从
React/Vue 按页切流校验改为默认运行链路校验。
"""

from __future__ import annotations

from pathlib import Path


REQUIRED_VUE_ROUTES = {
    "/chat",
    "/dashboard",
    "/dashboard/:symbol",
    "/workbench",
    "/rag-inspector",
    "/watchlist",
    "/portfolio",
    "/reports",
    "/alerts",
    "/welcome",
}


def _read(repo_root: Path, relative: str) -> str:
    return (repo_root / relative).read_text(encoding="utf-8")


def _service_block(compose: str, service: str) -> str:
    """Extract one top-level Compose service block without requiring a YAML dependency."""
    lines = compose.splitlines()
    marker = f"  {service}:"
    try:
        start = lines.index(marker)
    except ValueError:
        return ""

    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.startswith("  ") and not line.startswith("    ") and line.strip().endswith(":"):
            end = index
            break
    return "\n".join(lines[start:end])


def validate_python_vue_stack(repo_root: Path) -> list[str]:
    """返回默认 Python + Vue 链路的静态校验错误列表。"""
    errors: list[str] = []

    compose = _read(repo_root, "docker-compose.yml")
    dev_compose = _read(repo_root, "docker-compose.dev.yml")
    smoke_compose = _read(repo_root, "docker-compose.smoke.yml")
    vue_nginx = _read(repo_root, "frontend-vue/nginx.conf")
    runtime = _read(repo_root, "frontend-vue/src/config/runtime.ts")
    router = _read(repo_root, "frontend-vue/src/router/index.ts")
    release_gate = _read(repo_root, "scripts/release_gate.ps1")
    release_gate_sh = _read(repo_root, "scripts/release_gate.sh")
    ci_workflow = _read(repo_root, ".github/workflows/ci.yml")

    if "spring-backend:" in compose:
        errors.append("docker-compose.yml must not define spring-backend as a default service")
    if "backend-spring" in compose:
        errors.append("docker-compose.yml must not build backend-spring")
    if "context: ./frontend-vue" not in compose:
        errors.append("docker-compose.yml frontend service must build frontend-vue")
    if '"8000:8000"' in compose or "'8000:8000'" in compose:
        errors.append("docker-compose.yml must not expose backend 8000 by default")
    if '"5174:8080"' in compose or "'5174:8080'" in compose:
        errors.append("docker-compose.yml must not expose Vue dev port by default")
    if '"8000:8000"' not in dev_compose and "'8000:8000'" not in dev_compose:
        errors.append("docker-compose.dev.yml must expose backend 8000 for local debugging")
    if '"5174:8080"' not in dev_compose and "'5174:8080'" not in dev_compose:
        errors.append("docker-compose.dev.yml must expose Vue frontend on 5174 for local debugging")
    if "container_name: finsight-smoke-frontend" not in smoke_compose:
        errors.append("docker-compose.smoke.yml must isolate frontend container name")
    if "ports: !override" not in smoke_compose:
        errors.append("docker-compose.smoke.yml frontend ports must use !override to avoid exposing host port 80")
    if '"18080:8080"' not in smoke_compose and "'18080:8080'" not in smoke_compose:
        errors.append("docker-compose.smoke.yml must expose smoke frontend on host port 18080")
    for volume_name in (
        "finsight_smoke_postgres_data",
        "finsight_smoke_backend_data",
        "finsight_smoke_backend_logs",
        "finsight_smoke_model_cache",
    ):
        if volume_name not in smoke_compose:
            errors.append(f"docker-compose.smoke.yml missing isolated volume: {volume_name}")
    if "name: finsight-smoke-net" not in smoke_compose:
        errors.append("docker-compose.smoke.yml must use isolated network finsight-smoke-net")
    if "spring-backend" in vue_nginx:
        errors.append("frontend-vue/nginx.conf must proxy to backend:8000, not spring-backend")
    if "http://backend:8000" not in vue_nginx:
        errors.append("frontend-vue/nginx.conf must proxy API traffic to backend:8000")
    if "127.0.0.1:8000" not in runtime:
        errors.append("frontend-vue runtime default must target FastAPI 8000 in local dev")
    if "127.0.0.1:8080" in runtime:
        errors.append("frontend-vue runtime must not default to Spring 8080")
    if 'Push-Location "frontend-vue"' not in release_gate:
        errors.append("release_gate.ps1 must run frontend-vue as the default frontend")
    if "backend-spring/pom.xml" in release_gate:
        errors.append("release_gate.ps1 must not run backend-spring as a default gate")
    if "pushd frontend-vue" not in release_gate_sh:
        errors.append("release_gate.sh must run frontend-vue as the default frontend")
    if "backend-spring/pom.xml" in release_gate_sh:
        errors.append("release_gate.sh must not run backend-spring as a default gate")
    if "frontend/package-lock.json" in ci_workflow or "--prefix frontend\n" in ci_workflow:
        errors.append(".github/workflows/ci.yml must not run the deleted React frontend")
    if "working-directory: frontend\n" in ci_workflow or "frontend/dist/" in ci_workflow:
        errors.append(".github/workflows/ci.yml artifacts and working directories must use frontend-vue")
    if "frontend-vue/package-lock.json" not in ci_workflow:
        errors.append(".github/workflows/ci.yml must cache frontend-vue dependencies")

    hardening_requirements = {
        "postgres": (
            "dockerfile: docker/postgres.Dockerfile",
            "security_opt:",
            "no-new-privileges:true",
            "read_only: true",
            "/var/run/postgresql:",
            "/tmp:",
        ),
        "backend": (
            "security_opt:",
            "no-new-privileges:true",
            "cap_drop:",
            "- ALL",
            "read_only: true",
            "/tmp:",
            "/app/backend/data:",
            'test: ["CMD", "python", "-c"',
        ),
        "frontend": (
            "security_opt:",
            "no-new-privileges:true",
            "cap_drop:",
            "- ALL",
            "read_only: true",
            "/var/cache/nginx:",
            "/run:",
            "/tmp:",
        ),
    }
    for service, required_tokens in hardening_requirements.items():
        block = _service_block(compose, service)
        for token in required_tokens:
            if token not in block:
                errors.append(f"docker-compose.yml {service} runtime hardening missing: {token}")

    for route in sorted(REQUIRED_VUE_ROUTES):
        if f"path: '{route}'" not in router:
            errors.append(f"frontend-vue router missing required route: {route}")

    return errors


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    try:
        errors = validate_python_vue_stack(repo_root)
    except Exception as exc:
        print(f"[python-vue-stack] FAIL: {exc}")
        return 1

    if errors:
        print("[python-vue-stack] FAIL")
        for item in errors:
            print(f"  - {item}")
        return 1

    print("[python-vue-stack] OK (default chain: frontend-vue -> backend/FastAPI)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
