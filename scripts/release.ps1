# 本地构建绿色包。不会 push，不会上传 GitHub Release。
# 编码: UTF-8 with BOM（Windows PowerShell 5.1 显示中文）
# 用法:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\release.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\release.ps1 -CheckOnly
param(
    [switch]$CheckOnly,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Write-Step([string]$msg) {
    Write-Host ""
    Write-Host "==> $msg" -ForegroundColor Cyan
}

function Get-AppVersion {
    $py = Join-Path $Root ".venv\Scripts\python.exe"
    if (-not (Test-Path $py)) { $py = "python" }
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $ver = & $py -c "from pdf_dewatermark import __version__; print(__version__)" 2>$null
    $ErrorActionPreference = $old
    if (-not $ver) {
        $init = Join-Path $Root "src\pdf_dewatermark\__init__.py"
        if (Test-Path $init) {
            $m = Select-String -Path $init -Pattern '__version__\s*=\s*"([^"]+)"' | Select-Object -First 1
            if ($m) { return $m.Matches.Groups[1].Value }
        }
        return "0.0.0"
    }
    return ([string]$ver).Trim()
}

Write-Host "净页 JingYe - 本地构建（不上传）"
Write-Host "项目目录: $Root"

Write-Step "检查工作区"
if (Test-Path .git) {
    $oldEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $trackedDanger = @()
    foreach ($p in @("dist", "build", ".venv")) {
        $t = & git ls-files $p 2>$null
        if ($t) { $trackedDanger += $t }
    }
    if ($trackedDanger) {
        Write-Warning "以下路径已被 Git 跟踪（通常应忽略）:"
        $trackedDanger | Select-Object -First 20 | ForEach-Object { Write-Host "  $_" }
        Write-Host "可考虑: git rm -r --cached dist build"
    } else {
        Write-Host "未跟踪 dist/build/.venv，正常。"
    }
    $pdfTracked = & git ls-files "*.pdf" 2>$null
    if ($pdfTracked) {
        Write-Warning "有 PDF 被跟踪:"
        $pdfTracked | ForEach-Object { Write-Host "  $_" }
    }
    $ErrorActionPreference = $oldEap
} else {
    Write-Host "尚不是 Git 仓库（仅影响检查，仍可构建）。"
}

if ($CheckOnly) {
    Write-Host "仅检查结束。"
    exit 0
}

$ver = Get-AppVersion
Write-Host "版本: $ver"
$zipPath = Join-Path $Root "dist\releases\JingYe-$ver.zip"

if (-not $SkipBuild) {
    Write-Step "构建绿色目录与 zip"
    Get-Process -Name "JingYe" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    $buildScript = Join-Path $Root "scripts\build_gui_onedir.ps1"
    powershell -NoProfile -ExecutionPolicy Bypass -File $buildScript
    if ($LASTEXITCODE -ne 0) { Write-Error "构建失败。" }
    if (-not (Test-Path -LiteralPath $zipPath)) {
        Write-Error "构建后未找到 zip: $zipPath"
    }
    $sizeMb = [math]::Round((Get-Item -LiteralPath $zipPath).Length / 1MB, 2)
    Write-Host "完成: $zipPath ($sizeMb MB)"
} else {
    if (-not (Test-Path -LiteralPath $zipPath)) {
        Write-Error "SkipBuild 但 zip 不存在: $zipPath"
    }
    Write-Host "使用已有 zip: $zipPath"
}

Write-Step "说明"
Write-Host "本脚本只生成本地包，不会 git push，也不会上传 GitHub Release。"
Write-Host "若要发安装包: 浏览器打开仓库 Releases，手动上传上述 zip。"
Write-Host "源码推送请自行: git push -u origin main"
Write-Host "完毕。"
