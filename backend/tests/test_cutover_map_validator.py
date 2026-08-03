from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_cutover_map.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_cutover_map", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_repo_default_stack_is_python_vue():
    module = _load_module()
    errors = module.validate_python_vue_stack(REPO_ROOT)
    assert errors == []


def test_validator_rejects_spring_default_markers(tmp_path):
    module = _load_module()

    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / "frontend-vue/src/config").mkdir(parents=True)
    (tmp_path / "frontend-vue/src/router").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()

    (tmp_path / "docker-compose.yml").write_text(
        "services:\n  spring-backend:\n    build: ./backend-spring\n",
        encoding="utf-8",
    )
    (tmp_path / "docker-compose.dev.yml").write_text(
        'services:\n  backend:\n    ports:\n      - "8000:8000"\n  frontend:\n    ports:\n      - "5174:8080"\n',
        encoding="utf-8",
    )
    (tmp_path / "docker-compose.smoke.yml").write_text(
        'services:\n'
        '  frontend:\n'
        '    container_name: finsight-smoke-frontend\n'
        '    ports: !override\n'
        '      - "18080:8080"\n'
        'volumes:\n'
        '  postgres_data:\n'
        '    name: finsight_smoke_postgres_data\n'
        '  backend_data:\n'
        '    name: finsight_smoke_backend_data\n'
        '  backend_logs:\n'
        '    name: finsight_smoke_backend_logs\n'
        '  model_cache:\n'
        '    name: finsight_smoke_model_cache\n'
        'networks:\n'
        '  finsight-net:\n'
        '    name: finsight-smoke-net\n',
        encoding="utf-8",
    )
    (tmp_path / "frontend-vue/nginx.conf").write_text(
        "proxy_pass http://spring-backend:8080;",
        encoding="utf-8",
    )
    (tmp_path / "frontend-vue/src/config/runtime.ts").write_text(
        "const DEFAULT_API_BASE_URL = 'http://127.0.0.1:8080';",
        encoding="utf-8",
    )
    (tmp_path / "frontend-vue/src/router/index.ts").write_text(
        "\n".join(f"path: '{route}'" for route in module.REQUIRED_VUE_ROUTES),
        encoding="utf-8",
    )
    (tmp_path / "scripts/release_gate.ps1").write_text(
        'Push-Location "frontend"',
        encoding="utf-8",
    )
    (tmp_path / "scripts/release_gate.sh").write_text(
        "pushd frontend > /dev/null\n",
        encoding="utf-8",
    )
    (tmp_path / ".github/workflows/ci.yml").write_text(
        "cache-dependency-path: frontend/package-lock.json\n"
        "run: npm ci --prefix frontend\n"
        "working-directory: frontend\n"
        "path: frontend/dist/\n",
        encoding="utf-8",
    )

    errors = module.validate_python_vue_stack(tmp_path)
    assert any("spring-backend" in item for item in errors)
    assert any("Spring 8080" in item for item in errors)
    assert any("frontend-vue" in item for item in errors)
    assert any("deleted React frontend" in item for item in errors)


def test_validator_rejects_default_host_port_exposure(tmp_path):
    module = _load_module()

    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / "frontend-vue/src/config").mkdir(parents=True)
    (tmp_path / "frontend-vue/src/router").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()

    (tmp_path / "docker-compose.yml").write_text(
        'services:\n'
        '  backend:\n'
        '    ports: !override\n'
        '      - "8000:8000"\n'
        '  frontend:\n'
        '    build:\n'
        '      context: ./frontend-vue\n'
        '    ports:\n'
        '      - "5174:8080"\n',
        encoding="utf-8",
    )
    (tmp_path / "docker-compose.dev.yml").write_text(
        "services:\n  backend:\n    environment:\n      DEV_MODE: '1'\n",
        encoding="utf-8",
    )
    (tmp_path / "docker-compose.smoke.yml").write_text(
        'services:\n'
        '  frontend:\n'
        '    container_name: finsight-smoke-frontend\n'
        '    ports:\n'
        '      - "18080:8080"\n'
        'volumes:\n'
        '  postgres_data:\n'
        '    name: finsight_smoke_postgres_data\n'
        '  backend_data:\n'
        '    name: finsight_smoke_backend_data\n'
        '  backend_logs:\n'
        '    name: finsight_smoke_backend_logs\n'
        '  model_cache:\n'
        '    name: finsight_smoke_model_cache\n'
        'networks:\n'
        '  finsight-net:\n'
        '    name: finsight-smoke-net\n',
        encoding="utf-8",
    )
    (tmp_path / "frontend-vue/nginx.conf").write_text(
        "proxy_pass http://backend:8000;",
        encoding="utf-8",
    )
    (tmp_path / "frontend-vue/src/config/runtime.ts").write_text(
        "const DEFAULT_API_BASE_URL = 'http://127.0.0.1:8000';",
        encoding="utf-8",
    )
    (tmp_path / "frontend-vue/src/router/index.ts").write_text(
        "\n".join(f"path: '{route}'" for route in module.REQUIRED_VUE_ROUTES),
        encoding="utf-8",
    )
    (tmp_path / "scripts/release_gate.ps1").write_text(
        'Push-Location "frontend-vue"',
        encoding="utf-8",
    )
    (tmp_path / "scripts/release_gate.sh").write_text(
        "pushd frontend-vue > /dev/null\n",
        encoding="utf-8",
    )
    (tmp_path / ".github/workflows/ci.yml").write_text(
        "cache-dependency-path: frontend-vue/package-lock.json\n"
        "run: npm ci --prefix frontend-vue\n"
        "path: frontend-vue/dist/\n",
        encoding="utf-8",
    )

    errors = module.validate_python_vue_stack(tmp_path)
    assert any("must not expose backend 8000" in item for item in errors)
    assert any("must not expose Vue dev port" in item for item in errors)
    assert any("docker-compose.dev.yml must expose backend 8000" in item for item in errors)
    assert any("docker-compose.dev.yml must expose Vue frontend" in item for item in errors)
    assert any("postgres runtime hardening missing" in item for item in errors)
    assert any("backend runtime hardening missing" in item for item in errors)
    assert any("frontend runtime hardening missing" in item for item in errors)


def test_validator_rejects_unsafe_smoke_compose(tmp_path):
    module = _load_module()

    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / "frontend-vue/src/config").mkdir(parents=True)
    (tmp_path / "frontend-vue/src/router").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()

    (tmp_path / "docker-compose.yml").write_text(
        'services:\n  frontend:\n    build:\n      context: ./frontend-vue\n',
        encoding="utf-8",
    )
    (tmp_path / "docker-compose.dev.yml").write_text(
        'services:\n  backend:\n    ports:\n      - "8000:8000"\n  frontend:\n    ports:\n      - "5174:8080"\n',
        encoding="utf-8",
    )
    (tmp_path / "docker-compose.smoke.yml").write_text(
        'services:\n  frontend:\n    ports:\n      - "80:8080"\n',
        encoding="utf-8",
    )
    (tmp_path / "frontend-vue/nginx.conf").write_text(
        "proxy_pass http://backend:8000;",
        encoding="utf-8",
    )
    (tmp_path / "frontend-vue/src/config/runtime.ts").write_text(
        "const DEFAULT_API_BASE_URL = 'http://127.0.0.1:8000';",
        encoding="utf-8",
    )
    (tmp_path / "frontend-vue/src/router/index.ts").write_text(
        "\n".join(f"path: '{route}'" for route in module.REQUIRED_VUE_ROUTES),
        encoding="utf-8",
    )
    (tmp_path / "scripts/release_gate.ps1").write_text(
        'Push-Location "frontend-vue"',
        encoding="utf-8",
    )
    (tmp_path / "scripts/release_gate.sh").write_text(
        "pushd frontend-vue > /dev/null\n",
        encoding="utf-8",
    )
    (tmp_path / ".github/workflows/ci.yml").write_text(
        "cache-dependency-path: frontend-vue/package-lock.json\n"
        "run: npm ci --prefix frontend-vue\n"
        "path: frontend-vue/dist/\n",
        encoding="utf-8",
    )

    errors = module.validate_python_vue_stack(tmp_path)
    assert any("isolate frontend container name" in item for item in errors)
    assert any("ports must use !override" in item for item in errors)
    assert any("host port 18080" in item for item in errors)
    assert any("finsight_smoke_postgres_data" in item for item in errors)
    assert any("finsight-smoke-net" in item for item in errors)
