#!/usr/bin/env bash
# scripts/release_gate.sh — POSIX equivalent of release_gate.ps1.
# Linux/macOS users / CI runners that prefer bash use this.
#
# Usage:
#   bash scripts/release_gate.sh              # default: backend/tests + frontend 4-step
#   bash scripts/release_gate.sh --all        # also run tests/ top-level
#   bash scripts/release_gate.sh --skip-backend
#   bash scripts/release_gate.sh --skip-frontend
#   bash scripts/release_gate.sh --smoke-only # import smoke + Vue build only
#   bash scripts/release_gate.sh --with-e2e   # add Vue Playwright smoke
set -euo pipefail
cd "$(dirname "$0")/.."

ALL=0
SKIP_BACKEND=0
SKIP_FRONTEND=0
SMOKE_ONLY=0
WITH_E2E=0
WITH_VUE=0
BASETEMP=".pytest-basetemp-release-gate"

for arg in "$@"; do
  case "$arg" in
    --all) ALL=1 ;;
    --skip-backend) SKIP_BACKEND=1 ;;
    --skip-frontend) SKIP_FRONTEND=1 ;;
    --smoke-only) SMOKE_ONLY=1 ;;
    --with-e2e) WITH_E2E=1 ;;
    --with-vue) WITH_VUE=1 ;; # 兼容旧命令: Vue 已默认执行。
    *) echo "Unknown flag: $arg"; exit 2 ;;
  esac
done

declare -a STEPS=()
declare -a CODES=()
declare -a DURATIONS=()
TOTAL_START=$(date +%s)

run_step() {
  local name="$1"; shift
  local t0=$(date +%s)
  echo
  echo "==> [$(date +%H:%M:%S)] ${name}"
  set +e
  ( "$@" )
  local code=$?
  set -e
  local dur=$(( $(date +%s) - t0 ))
  local status="PASS"
  if [ "$code" -ne 0 ]; then status="FAIL($code)"; fi
  echo "    -> ${status}  (${dur}s)"
  STEPS+=("$name"); CODES+=("$code"); DURATIONS+=("$dur")
}

# Pick python interpreter
if [ -x ".venv/bin/python" ]; then PY=".venv/bin/python"
elif [ -x ".venv/Scripts/python.exe" ]; then PY=".venv/Scripts/python.exe"
else PY="python"; fi

if [ "$SKIP_BACKEND" -eq 0 ]; then
  DEV_MODE="${DEV_MODE:-true}" run_step "backend.import-smoke" "$PY" -c '
from backend.api.main import app
from fastapi.testclient import TestClient
with TestClient(app) as c:
    r = c.get("/health")
    assert r.status_code == 200, f"/health endpoint failed: {r.status_code}"
print("import + /health OK")'

  if [ "$SMOKE_ONLY" -eq 0 ]; then
    STAMP=$(date +%Y%m%d%H%M%S)
    if [ "$ALL" -eq 1 ]; then
      run_step "backend.pytest-full" "$PY" -m pytest -q -p no:cacheprovider --basetemp="${BASETEMP}-full-${STAMP}" backend/tests tests
    else
      run_step "backend.pytest-core" "$PY" -m pytest -q -p no:cacheprovider --basetemp="${BASETEMP}-core-${STAMP}" backend/tests
    fi
  fi
fi

if [ "$SKIP_FRONTEND" -eq 0 ]; then
  pushd frontend-vue > /dev/null
  if [ "$SMOKE_ONLY" -eq 0 ]; then
    run_step "vue.lint" npm run lint
    run_step "vue.typecheck" npm run typecheck
  fi
  run_step "vue.build" npm run build
  if [ "$WITH_E2E" -eq 1 ] && [ "$SMOKE_ONLY" -eq 0 ]; then
    run_step "vue.e2e-pages" npm run test:e2e
  fi
  popd > /dev/null
fi

TOTAL=$(( $(date +%s) - TOTAL_START ))
FAILED=0
echo
echo "================================================================"
echo " Release Gate Summary  (${#STEPS[@]} steps, ${TOTAL}s)"
echo "================================================================"
for i in "${!STEPS[@]}"; do
  code="${CODES[$i]}"
  status="PASS"
  if [ "$code" -ne 0 ]; then status="FAIL($code)"; FAILED=$((FAILED+1)); fi
  printf "  %-32s %-10s %ss\n" "${STEPS[$i]}" "$status" "${DURATIONS[$i]}"
done

echo
if [ "$FAILED" -eq 0 ]; then
  echo " RESULT: ALL GREEN - release gate passed."
  exit 0
else
  echo " RESULT: $FAILED step(s) FAILED — release gate blocked."
  exit "$FAILED"
fi
