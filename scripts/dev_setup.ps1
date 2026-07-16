# Create venv, install package with GUI + dev extras.
# Usage (from anywhere):
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\dev_setup.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "==> Project: $Root"

$pyLauncher = $null
foreach ($c in @("py -3.12", "py -3", "python")) {
    try {
        if ($c -match "^py ") {
            $parts = $c.Split(" ")
            & $parts[0] $parts[1] -c "import sys; print(sys.version)" | Out-Null
            if ($LASTEXITCODE -eq 0) { $pyLauncher = $c; break }
        } else {
            & $c -c "import sys; print(sys.version)" | Out-Null
            if ($LASTEXITCODE -eq 0) { $pyLauncher = $c; break }
        }
    } catch { }
}
if (-not $pyLauncher) {
    Write-Error "Python not found. Install Python 3.10+ and retry."
}

Write-Host "==> Using: $pyLauncher"

$venvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Host "==> Creating .venv ..."
    if ($pyLauncher -match "^py ") {
        $parts = $pyLauncher.Split(" ")
        & $parts[0] $parts[1] -m venv .venv
    } else {
        & $pyLauncher -m venv .venv
    }
}

if (-not (Test-Path $venvPy)) {
    Write-Error "Failed to create .venv"
}

Write-Host "==> Upgrading pip ..."
& $venvPy -m pip install -U pip wheel setuptools

Write-Host "==> Installing editable package [gui,dev] ..."
& $venvPy -m pip install -e ".[gui,dev]"

Write-Host ""
Write-Host "OK. Activate and run:"
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host "  python -m pdf_dewatermark"
Write-Host "  or: .\run_gui.bat"
