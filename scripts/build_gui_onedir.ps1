# Build green onedir package for JingYe.
# Strategy:
#   dist/JingYe/                 -> always latest (overwrite)
#   dist/releases/JingYe-x.y.z/  -> versioned archive
#   dist/releases/JingYe-x.y.z.zip
#
# IMPORTANT: Do NOT put Chinese string literals in this .ps1 for filenames.
# Windows PowerShell 5.1 often mis-decodes script encoding and corrupts names.
# All Chinese text/files are written by packaging/*.py with utf-8-sig.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "Project root: $Root"
$py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    $py = "python"
    Write-Host "Warning: .venv not found, using system python"
}

$ver = & $py -c "from pdf_dewatermark import __version__; print(__version__)"
if (-not $ver) { $ver = "0.0.0" }
$ver = $ver.Trim()
Write-Host "Version: $ver"

& $py -m pip install "pyinstaller>=6.0" -q
$spec = Join-Path $Root "packaging\pdf_dewatermark_gui.spec"
& $py -m PyInstaller --noconfirm --clean $spec

$dist = Join-Path $Root "dist\JingYe"
if (-not (Test-Path $dist)) {
    Write-Error "Build finished but dist folder not found: $dist"
}

# Write Chinese meta via Python (UTF-8 BOM + correct Unicode filenames)
& $py (Join-Path $Root "packaging\write_dist_meta.py") $dist $ver
if ($LASTEXITCODE -ne 0) {
    Write-Error "write_dist_meta.py failed"
}

# Versioned release copy (ASCII path only)
$relRoot = Join-Path $Root "dist\releases"
$relDirName = "JingYe-$ver"
$relDir = Join-Path $relRoot $relDirName
New-Item -ItemType Directory -Force -Path $relRoot | Out-Null
if (Test-Path -LiteralPath $relDir) {
    Write-Host "Refreshing release folder: $relDir"
    Remove-Item -LiteralPath $relDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $relDir | Out-Null
# Robocopy/copy via Python for Unicode-safe tree
& $py -c @"
import shutil
from pathlib import Path
src = Path(r'''$dist''')
dst = Path(r'''$relDir''')
if dst.exists():
    shutil.rmtree(dst)
shutil.copytree(src, dst, dirs_exist_ok=False)
print('copied to', dst)
"@

$zipPath = Join-Path $relRoot ("JingYe-{0}.zip" -f $ver)
& $py (Join-Path $Root "packaging\make_release_zip.py") $relDir $zipPath
if ($LASTEXITCODE -ne 0) {
    Write-Error "make_release_zip.py failed"
}

Write-Host ""
Write-Host "OK latest : $dist\JingYe.exe"
Write-Host "OK release: $relDir"
Write-Host "OK zip    : $zipPath"
Write-Host "Files: VERSION.txt, README.txt, and Chinese readme written by Python (utf-8-sig)"
