# ubisam-mail-mcp 원클릭 설치 + setup wizard (Windows 데스크톱 앱용)
#
# 사용법 (레포를 clone 한 뒤 레포 안에서):
#   powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
#
# 하는 일: Python 3.10+ 자동 탐색 -> .venv 생성 -> pip install -e . -> setup wizard(--web-setup) 실행

$ErrorActionPreference = "Stop"

# 레포 루트(이 스크립트의 상위 폴더)로 이동
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot
Write-Host "[ubisam-mail-mcp] 작업 폴더: $RepoRoot" -ForegroundColor Cyan

# 1) Python 3.10+ 탐색 (py 런처로 3.12 -> 3.11 -> 3.10 순, 없으면 py -3 검사)
function Find-PyArg {
    # 함수 스코프에서만 에러를 무시해, 없는 버전 탐색이 스크립트를 중단시키지 않게 함
    $ErrorActionPreference = "SilentlyContinue"
    foreach ($v in @("3.12", "3.11", "3.10")) {
        try {
            & py "-$v" --version *> $null
            if ($LASTEXITCODE -eq 0) { return "-$v" }
        } catch { }
    }
    try {
        $ver = & py -3 -c "import sys;print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and $ver) {
            $p = $ver.Trim().Split(".")
            if (([int]$p[0] -eq 3) -and ([int]$p[1] -ge 10)) { return "-3" }
        }
    } catch { }
    return $null
}

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    Write-Host "Python(py 런처)이 없습니다. 먼저 설치하세요:" -ForegroundColor Yellow
    Write-Host "  winget install Python.Python.3.12"
    exit 1
}

$PyArg = Find-PyArg
if (-not $PyArg) {
    Write-Host "Python 3.10 이상을 찾지 못했습니다. 설치 후 다시 실행하세요:" -ForegroundColor Yellow
    Write-Host "  winget install Python.Python.3.12"
    exit 1
}
Write-Host "[1/4] 사용할 Python: py $PyArg" -ForegroundColor Green

# 2) .venv 생성 (이미 있으면 재사용)
$VenvPy = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (Test-Path $VenvPy) {
    Write-Host "[2/4] 기존 .venv 재사용 (새로 만들려면 'Remove-Item -Recurse -Force .venv' 후 재실행)" -ForegroundColor Green
} else {
    Write-Host "[2/4] .venv 생성 중..." -ForegroundColor Green
    & py $PyArg -m venv .venv
    if ($LASTEXITCODE -ne 0) { Write-Host ".venv 생성 실패." -ForegroundColor Red; exit 1 }
}

# 3) 편집 설치
Write-Host "[3/4] 패키지 설치 중 (pip install -e .)..." -ForegroundColor Green
& $VenvPy -m pip install --upgrade pip
& $VenvPy -m pip install -e .
if ($LASTEXITCODE -ne 0) { Write-Host "설치 실패." -ForegroundColor Red; exit 1 }

# 4) setup wizard 실행 (브라우저 기반 웹 setup)
Write-Host "[4/4] setup wizard 실행 (--web-setup). 브라우저가 안 열리면 터미널의 http://127.0.0.1:8765/ 주소를 직접 여세요." -ForegroundColor Green
& $VenvPy -m ubisam_mail_mcp.setup_wizard --web-setup
