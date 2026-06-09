# scripts/release_gate.ps1
# ---------------------------------------------------------------
# FinSight Release Gate — 一键串起 Python 后端 + Vue 前端的上线门禁。
#
# 涵盖:
#   * Backend : pytest backend/tests (默认),可加 -All 跑 tests/* 全量
#   * Backend : 关键 import smoke (FastAPI app 启动 + /health)
#   * Vue     : frontend-vue lint/typecheck/build (+e2e if -WithE2E)
#
# 用法:
#   pwsh scripts/release_gate.ps1            # 默认 backend/tests + 前端 4 件套
#   pwsh scripts/release_gate.ps1 -All       # 加跑 tests/ 顶层全量
#   pwsh scripts/release_gate.ps1 -SkipBackend
#   pwsh scripts/release_gate.ps1 -SkipFrontend
#   pwsh scripts/release_gate.ps1 -SmokeOnly # 只跑 import + Vue build
#   pwsh scripts/release_gate.ps1 -WithE2E   # 加跑 Vue Playwright
#
# 退出码:
#   0 = 全部通过, 否则 = 失败的步骤数
# ---------------------------------------------------------------

[CmdletBinding()]
param(
    [switch]$All,
    [switch]$SkipBackend,
    [switch]$SkipFrontend,
    [switch]$SmokeOnly,
    [switch]$WithE2E,
    # 兼容旧命令: Vue 已是默认前端, 传 -WithVue 不改变行为。
    [switch]$WithVue,
    [string]$PytestBaseTemp = ".pytest-basetemp-release-gate"
)

$ErrorActionPreference = "Continue"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

$results = New-Object System.Collections.Generic.List[PSObject]
$startTime = Get-Date
$python = if (Test-Path ".venv/Scripts/python.exe") { ".venv/Scripts/python.exe" } else { "python" }

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Script
    )
    $t0 = Get-Date
    Write-Host ""
    Write-Host "==> [$(Get-Date -Format HH:mm:ss)] $Name" -ForegroundColor Cyan
    try {
        & $Script
        $code = $LASTEXITCODE
        if ($null -eq $code) { $code = 0 }
    } catch {
        Write-Host $_ -ForegroundColor Red
        $code = 99
    }
    $duration = ((Get-Date) - $t0).TotalSeconds
    $status = if ($code -eq 0) { "PASS" } else { "FAIL($code)" }
    $color = if ($code -eq 0) { "Green" } else { "Red" }
    Write-Host "    -> $status  (${duration}s)" -ForegroundColor $color
    $results.Add([PSCustomObject]@{
        Step     = $Name
        Status   = $status
        Code     = $code
        Duration = [math]::Round($duration, 1)
    }) | Out-Null
}

# ── Backend ─────────────────────────────────────────────────────

if (-not $SkipBackend) {
    # Always run import smoke first — catches missing dependencies fast
    Invoke-Step "backend.import-smoke" {
        $env:DEV_MODE = "true"        # bypass prod env-var gate during smoke
        & $python -c @"
from backend.api.main import app
from fastapi.testclient import TestClient

with TestClient(app) as c:
    r = c.get('/health')
    assert r.status_code == 200, f'/health endpoint failed: {r.status_code}'
print('import + /health OK')
"@
    }

    if (-not $SmokeOnly) {
        # 使用 v2 basetemp, 避开旧脚本留下的 Windows 锁目录。
        # Windows PowerShell 5 在这里直接嵌套 if/else 时会误报解析错误; 保留一条普通语句稳定解析。
        $tempMarker = $null
        if ($All) {
            $tempName = ".pytest-basetemp-release-gate-full-v2"
            $tempPath = Join-Path $repoRoot $tempName
            Write-Host "    pytest basetemp: $tempPath" -ForegroundColor DarkGray
            Invoke-Step "backend.pytest-full" {
                & $python -m pytest -q -p no:cacheprovider --basetemp="$tempPath" backend/tests tests
            }
        } else {
            $tempName = ".pytest-basetemp-release-gate-core-v2"
            $tempPath = Join-Path $repoRoot $tempName
            Write-Host "    pytest basetemp: $tempPath" -ForegroundColor DarkGray
            Invoke-Step "backend.pytest-core" {
                & $python -m pytest -q -p no:cacheprovider --basetemp="$tempPath" backend/tests
            }
        }
    }
}

# ── Frontend ────────────────────────────────────────────────────

if (-not $SkipFrontend) {
    Push-Location "frontend-vue"
    try {
        $npm = "npm.cmd"

        if (-not $SmokeOnly) {
            Invoke-Step "vue.lint" { & $npm run lint }
            Invoke-Step "vue.typecheck" { & $npm run typecheck }
        }
        Invoke-Step "vue.build" { & $npm run build }

        if ($WithE2E -and -not $SmokeOnly) {
            Invoke-Step "vue.e2e-pages" {
                & $npm run test:e2e
            }
        }
    } finally {
        Pop-Location
    }
}

# ── Summary ─────────────────────────────────────────────────────

$total = $results.Count
$failed = @($results | Where-Object { $_.Code -ne 0 }).Count
$totalDuration = ((Get-Date) - $startTime).TotalSeconds

Write-Host ""
Write-Host "================================================================" -ForegroundColor Yellow
Write-Host " Release Gate Summary  ($total steps, $($totalDuration.ToString('0.0'))s)" -ForegroundColor Yellow
Write-Host "================================================================" -ForegroundColor Yellow
$results | Format-Table -AutoSize Step, Status, Duration

if ($failed -eq 0) {
    Write-Host ""
    Write-Host " RESULT: ALL GREEN - release gate passed." -ForegroundColor Green
    exit 0
} else {
    Write-Host ""
    Write-Host (" RESULT: {0} STEP(S) FAILED — release gate blocked." -f $failed) -ForegroundColor Red
    exit $failed
}
