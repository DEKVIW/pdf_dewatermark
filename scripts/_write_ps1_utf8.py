# -*- coding: utf-8 -*-
"""One-shot helper: rewrite maintainer ps1 scripts as UTF-8 with BOM (PS 5.1 Chinese)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent

OPEN_SOURCE_INIT = r"""# 本地 Git 初始化（维护用）。不上传 GitHub Release。
# 编码: UTF-8 with BOM（Windows PowerShell 5.1 显示中文）
# 用法:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\open_source_init.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Write-Step([string]$msg) {
    Write-Host ""
    Write-Host "==> $msg" -ForegroundColor Cyan
}

function Ask-YesNo([string]$Prompt, [bool]$DefaultYes = $true) {
    $hint = if ($DefaultYes) { "[Y/n]" } else { "[y/N]" }
    $r = Read-Host "$Prompt $hint"
    if ([string]::IsNullOrWhiteSpace($r)) { return $DefaultYes }
    return @("y", "yes", "Y", "YES") -contains $r.Trim()
}

function Get-GitRemoteUrl([string]$Name = "origin") {
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $out = & git remote get-url $Name 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) { return ([string]$out).Trim() }
        return $null
    } finally {
        $ErrorActionPreference = $old
    }
}

function Get-GitConfig([string]$Key) {
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $out = & git config $Key 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) { return ([string]$out).Trim() }
        return $null
    } finally {
        $ErrorActionPreference = $old
    }
}

Write-Host "净页 JingYe - 本地 Git 初始化（交互）"
Write-Host "项目目录: $Root"
Write-Host "说明: 只做本地 init / 远程 / 提交；不会上传安装包到 Release。"

Write-Step "检查 Git"
$oldEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$gitVer = & git --version 2>&1
$ErrorActionPreference = $oldEap
if ($LASTEXITCODE -ne 0) {
    Write-Error "未找到 Git，请安装: https://git-scm.com/"
}
Write-Host $gitVer

Write-Step "仓库"
if (-not (Test-Path (Join-Path $Root ".git"))) {
    if (Ask-YesNo "当前还不是 Git 仓库，是否执行 git init？") {
        $ErrorActionPreference = "Continue"
        git init
        git branch -M main 2>$null
        $ErrorActionPreference = "Stop"
        Write-Host "已初始化（分支 main）。"
    } else {
        Write-Host "已跳过 init，退出。"
        exit 0
    }
} else {
    Write-Host "已是 Git 仓库。"
}

$userName = Get-GitConfig "user.name"
$userEmail = Get-GitConfig "user.email"
if (-not $userName -or -not $userEmail) {
    Write-Host "尚未配置 git user.name / user.email。"
    Write-Host "示例:"
    Write-Host '  git config --global user.name "你的名字"'
    Write-Host '  git config --global user.email "you@example.com"'
    if (Ask-YesNo "是否现在为本仓库设置本地用户名和邮箱？" $false) {
        $n = Read-Host "user.name"
        $e = Read-Host "user.email"
        if ($n) { git config user.name $n }
        if ($e) { git config user.email $e }
    }
}

Write-Step "检查 .gitignore"
if (-not (Test-Path ".gitignore")) {
    Write-Warning "缺少 .gitignore！"
} else {
    Write-Host ".gitignore 存在。"
}

$danger = @()
if (Test-Path "dist") { $danger += "dist/（应忽略，勿提交）" }
if (Test-Path ".venv") { $danger += ".venv/（应忽略）" }
if (Test-Path "data/gui_prefs.json") { $danger += "data/gui_prefs.json（已忽略）" }
$pdfs = Get-ChildItem -Recurse -File -Filter "*.pdf" -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch "\\tests\\fixtures\\" } |
    Select-Object -First 5
if ($pdfs) {
    $danger += ("项目内 PDF 默认忽略: {0} ..." -f $pdfs[0].Name)
}
if ($danger.Count -gt 0) {
    Write-Host "本地存在以下内容（请勿 force add）:"
    $danger | ForEach-Object { Write-Host "  - $_" }
} else {
    Write-Host "未发现明显危险路径。"
}

Write-Step "远程 origin"
$existing = Get-GitRemoteUrl "origin"
if ($existing) {
    Write-Host "当前 origin 已配置: $existing"
    Write-Host "因此可以直接 git push，不必再次「配置远程」。"
    if (-not (Ask-YesNo "是否保留该远程？" $true)) {
        $ErrorActionPreference = "Continue"
        git remote remove origin
        $ErrorActionPreference = "Stop"
        $existing = $null
        Write-Host "已移除 origin。"
    }
}

if (-not $existing) {
    Write-Host ""
    Write-Host "请提供 GitHub 仓库地址，例如:"
    Write-Host "  https://github.com/你的用户名/pdf_dewatermark.git"
    Write-Host ""
    Write-Host "选项:"
    Write-Host "  1) 粘贴已在网页上建好的空仓库 URL"
    Write-Host "  2) 暂时不配置远程"
    $choice = Read-Host "请选择 1 或 2"
    if ($choice -eq "1") {
        $url = Read-Host "远程 URL"
        if ($url) {
            $url = $url.Trim()
            $ErrorActionPreference = "Continue"
            git remote add origin $url
            $code = $LASTEXITCODE
            $ErrorActionPreference = "Stop"
            if ($code -eq 0) {
                Write-Host "已添加 origin -> $url"
            } else {
                Write-Warning "git remote add 失败（可能已存在）。"
            }
        }
    } else {
        Write-Host "已跳过远程。以后可执行:"
        Write-Host "  git remote add origin https://github.com/USER/REPO.git"
    }
}

Write-Step "工作区状态"
$ErrorActionPreference = "Continue"
git status -sb
$ErrorActionPreference = "Stop"
Write-Host ""

if (Ask-YesNo "是否按安全路径执行 git add（源码/文档/脚本等）？" $true) {
    $ErrorActionPreference = "Continue"
    git add -- ".gitignore" "LICENSE" "README.md" "pyproject.toml" "requirements.txt" "run_gui.bat" 2>$null
    git add -- "src" "tests" "docs" "legacy" "packaging" "scripts" 2>$null
    git add -- "logs/.gitkeep" "output/.gitkeep" "data/.gitkeep" 2>$null
    Write-Host "已暂存，请核对（不应出现 dist / .venv / 用户 PDF）:"
    git status
    $ErrorActionPreference = "Stop"
    Write-Host ""
    if (Ask-YesNo "是否创建提交？" $true) {
        $ErrorActionPreference = "Continue"
        git commit -m "chore: update project files"
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "提交失败（可能没有变更，或未配置 user.name/email）。"
        }
        $ErrorActionPreference = "Stop"
    }
}

$originNow = Get-GitRemoteUrl "origin"
if ($originNow) {
    Write-Step "推送（可选）"
    Write-Host "远程: $originNow"
    Write-Host "将执行: git push -u origin <当前分支>"
    if (Ask-YesNo "现在推送到 origin？" $false) {
        $ErrorActionPreference = "Continue"
        $branch = (& git rev-parse --abbrev-ref HEAD 2>$null)
        if (-not $branch) { $branch = "main" }
        $branch = ([string]$branch).Trim()
        git push -u origin $branch
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "推送失败。请检查登录（HTTPS 用 Token）或 SSH 密钥。"
        }
        $ErrorActionPreference = "Stop"
    } else {
        Write-Host "已跳过推送。需要时执行:"
        Write-Host "  git push -u origin main"
    }
} else {
    Write-Host ""
    Write-Host "尚未配置 origin。配置后再推送:"
    Write-Host "  git remote add origin https://github.com/USER/REPO.git"
    Write-Host "  git push -u origin main"
}

Write-Step "完成"
Write-Host "本地绿色包构建（不上传）:"
Write-Host "  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_gui_onedir.ps1"
Write-Host "  或: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\release.ps1"
Write-Host "完毕。"
"""

RELEASE = r"""# 本地构建绿色包。不会 push，不会上传 GitHub Release。
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
"""


def main() -> None:
    files = {
        "open_source_init.ps1": OPEN_SOURCE_INIT,
        "release.ps1": RELEASE,
    }
    for name, text in files.items():
        path = ROOT / name
        # utf-8-sig => BOM for Windows PowerShell 5.1
        path.write_text(text.lstrip("\n"), encoding="utf-8-sig", newline="\r\n")
        bom = path.read_bytes()[:3] == b"\xef\xbb\xbf"
        print(f"wrote {path.name} BOM={bom}")


if __name__ == "__main__":
    main()
