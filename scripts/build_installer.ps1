# Build optional Windows installer (Inno Setup) from dist\JingYe onedir.
# Prerequisites:
#   1) Run scripts\build_gui_onedir.ps1 first (dist\JingYe must exist)
#   2) Install Inno Setup 6: https://jrsoftware.org/isinfo.php
#   3) ISCC.exe on PATH, or default install under Program Files
#
# Output: dist\releases\JingYe-Setup-x.y.z.exe
#
# Note: Do not put Chinese string literals in this .ps1 for filenames.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$dist = Join-Path $Root "dist\JingYe"
$exe = Join-Path $dist "JingYe.exe"
if (-not (Test-Path -LiteralPath $exe)) {
    Write-Error "Missing dist\JingYe\JingYe.exe. Run scripts\build_gui_onedir.ps1 first."
}

$py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
$ver = & $py -c "from pdf_dewatermark import __version__; print(__version__)"
$ver = $ver.Trim()
Write-Host "Version: $ver"

# Keep .iss AppVersion in sync (ASCII-only edit)
$iss = Join-Path $Root "packaging\jingye_setup.iss"
$issText = Get-Content -LiteralPath $iss -Raw -Encoding UTF8
if ($issText -notmatch [regex]::Escape("#define MyAppVersion `"$ver`"")) {
    $issText = [regex]::Replace(
        $issText,
        '#define MyAppVersion "[^"]*"',
        "#define MyAppVersion `"$ver`""
    )
    # Write UTF-8 without BOM for ISCC compatibility on some systems
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($iss, $issText, $utf8NoBom)
    Write-Host "Updated MyAppVersion in jingye_setup.iss -> $ver"
}

function Find-ISCC {
    $cmd = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "${env:LocalAppData}\Programs\Inno Setup 6\ISCC.exe"
    )
    foreach ($p in $candidates) {
        if ($p -and (Test-Path -LiteralPath $p)) { return $p }
    }
    return $null
}

$iscc = Find-ISCC
if (-not $iscc) {
    Write-Host ""
    Write-Host "Inno Setup 6 (ISCC.exe) not found."
    Write-Host "Install from: https://jrsoftware.org/isinfo.php"
    Write-Host "Then re-run: powershell -File scripts\build_installer.ps1"
    Write-Host ""
    Write-Host "Green package is already usable without installer:"
    Write-Host "  $exe"
    exit 2
}

Write-Host "Using ISCC: $iscc"
& $iscc $iss
if ($LASTEXITCODE -ne 0) {
    Write-Error "ISCC failed with exit code $LASTEXITCODE"
}

$setup = Join-Path $Root ("dist\releases\JingYe-Setup-{0}.exe" -f $ver)
if (Test-Path -LiteralPath $setup) {
    Write-Host "OK installer: $setup"
} else {
    Write-Host "ISCC finished; check dist\releases for JingYe-Setup-*.exe"
}
