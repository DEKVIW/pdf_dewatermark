# Build green package and optionally publish GitHub Release (latest zip only).
# Strategy A: source in Git; binary only on GitHub Releases (not committed).
#
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\release.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\release.ps1 -BuildOnly
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\release.ps1 -CheckOnly
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\release.ps1 -SkipBuild
param(
    [switch]$BuildOnly,
    [switch]$CheckOnly,
    [switch]$SkipBuild,
    [switch]$Yes
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Write-Step($msg) { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }
function Ask-YesNo([string]$Prompt, [bool]$DefaultYes = $true) {
    if ($Yes) { return $true }
    $hint = if ($DefaultYes) { "[Y/n]" } else { "[y/N]" }
    $r = Read-Host "$Prompt $hint"
    if ([string]::IsNullOrWhiteSpace($r)) { return $DefaultYes }
    return @("y", "yes", "Y", "YES") -contains $r.Trim()
}

function Get-AppVersion {
    $py = Join-Path $Root ".venv\Scripts\python.exe"
    if (-not (Test-Path $py)) { $py = "python" }
    $ver = & $py -c "from pdf_dewatermark import __version__; print(__version__)" 2>$null
    if (-not $ver) {
        $init = Join-Path $Root "src\pdf_dewatermark\__init__.py"
        if (Test-Path $init) {
            $m = Select-String -Path $init -Pattern '__version__\s*=\s*"([^"]+)"' | Select-Object -First 1
            if ($m) { return $m.Matches.Groups[1].Value }
        }
        return "0.0.0"
    }
    return $ver.Trim()
}

Write-Host "净页 JingYe - release helper"
Write-Host "Root: $Root"

# ----- check -----
Write-Step "Check working tree hygiene"
$badPatterns = @(
    "dist/",
    ".venv/",
    "build/",
    "data/gui_prefs.json"
)
if (Test-Path .git) {
    $oldEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $trackedDanger = @()
    foreach ($p in @("dist", "build", ".venv")) {
        $t = & git ls-files $p 2>$null
        if ($t) { $trackedDanger += $t }
    }
    if ($trackedDanger) {
        Write-Warning "These paths are TRACKED by git (should usually be ignored):"
        $trackedDanger | Select-Object -First 20 | ForEach-Object { Write-Host "  $_" }
        Write-Host "Consider: git rm -r --cached dist build"
    } else {
        Write-Host "No dist/build/.venv tracked. Good."
    }
    $pdfTracked = & git ls-files "*.pdf" 2>$null
    if ($pdfTracked) {
        Write-Warning "PDF files are tracked:"
        $pdfTracked | ForEach-Object { Write-Host "  $_" }
    }
    $ErrorActionPreference = $oldEap
} else {
    Write-Host "Not a git repo yet. Run scripts\open_source_init.ps1 first if you want remotes/tags."
}

if ($CheckOnly) {
    Write-Host "CheckOnly done."
    exit 0
}

$ver = Get-AppVersion
Write-Host "Version: $ver"
$zipPath = Join-Path $Root "dist\releases\JingYe-$ver.zip"
$tag = "v$ver"

# ----- build -----
if (-not $SkipBuild) {
    Write-Step "Build onedir + zip"
    # stop locking exe if possible
    Get-Process -Name "JingYe" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    $buildScript = Join-Path $Root "scripts\build_gui_onedir.ps1"
    powershell -NoProfile -ExecutionPolicy Bypass -File $buildScript
    if ($LASTEXITCODE -ne 0) { Write-Error "Build failed." }
    if (-not (Test-Path -LiteralPath $zipPath)) {
        Write-Error "Zip not found after build: $zipPath"
    }
    $sizeMb = [math]::Round((Get-Item -LiteralPath $zipPath).Length / 1MB, 2)
    Write-Host "Zip OK: $zipPath ($sizeMb MB)"
} else {
    if (-not (Test-Path -LiteralPath $zipPath)) {
        Write-Error "SkipBuild set but zip missing: $zipPath"
    }
    Write-Host "Using existing zip: $zipPath"
}

if ($BuildOnly) {
    Write-Host "BuildOnly done. Zip at: $zipPath"
    Write-Host "Upload manually via GitHub web UI -> Releases, or re-run without -BuildOnly."
    exit 0
}

# ----- git tag -----
Write-Step "Git tag $tag"
if (-not (Test-Path .git)) {
    Write-Warning "No .git — skip tag/release push. Zip is ready locally."
    exit 0
}

$oldEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& git rev-parse $tag 2>$null | Out-Null
$tagExists = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = $oldEap
if ($tagExists) {
    Write-Host "Tag $tag already exists."
} else {
    if (Ask-YesNo "Create git tag $tag on current HEAD?") {
        git tag -a $tag -m "Release $tag"
        Write-Host "Created tag $tag"
    }
}

# ----- GitHub Release -----
Write-Step "GitHub Release"
$gh = Get-Command gh -ErrorAction SilentlyContinue
if (-not $gh) {
    Write-Warning "GitHub CLI (gh) not installed."
    Write-Host "Install: https://cli.github.com/"
    Write-Host "Then: gh auth login"
    Write-Host ""
    Write-Host "Manual upload:"
    Write-Host "  1. Open your repo on github.com -> Releases -> Draft a new release"
    Write-Host "  2. Tag: $tag"
    Write-Host "  3. Attach file: $zipPath"
    Write-Host "  4. Publish"
    if (Ask-YesNo "Push git tag to origin only (no zip upload)?" $false) {
        git push origin $tag
    }
    exit 0
}

Write-Host "gh: $((gh --version | Select-Object -First 1))"
$auth = gh auth status 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Warning "gh not logged in. Run: gh auth login"
    Write-Host "Zip ready: $zipPath"
    exit 1
}

$oldEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$origin = (& git remote get-url origin 2>$null)
if ($LASTEXITCODE -ne 0) { $origin = $null }
$ErrorActionPreference = $oldEap
if (-not $origin) {
    Write-Warning "No origin remote. Run scripts\open_source_init.ps1"
    exit 1
}
Write-Host "origin: $origin"

if (Ask-YesNo "Push commits and tag to origin?") {
    $branch = (git rev-parse --abbrev-ref HEAD).Trim()
    git push origin $branch
    git push origin $tag 2>$null
    if ($LASTEXITCODE -ne 0) {
        # tag may already exist on remote
        git push origin $tag
    }
}

$notes = @"
## 净页 JingYe $ver

绿色免安装包：解压后运行 ``JingYe.exe``（请保留整个文件夹）。

- 使用说明（在线）：https://blog.yilanapp.com/posts/adbbe073/
- 源码与构建：见仓库 README
- 许可证：MIT

请仅处理你有权处理的文档。
"@

$notesFile = Join-Path $env:TEMP "jingye-release-notes-$ver.md"
Set-Content -Path $notesFile -Value $notes -Encoding UTF8

if (Ask-YesNo "Create/update GitHub Release $tag and upload zip?") {
    # If release exists, upload asset; else create
    gh release view $tag 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Release $tag exists, uploading asset (clobber)..."
        gh release upload $tag $zipPath --clobber
    } else {
        gh release create $tag $zipPath --title "净页 JingYe $ver" --notes-file $notesFile
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Error "gh release failed."
    }
    Write-Host "OK. Check Releases page on GitHub."
} else {
    Write-Host "Skipped GitHub Release. Local zip: $zipPath"
}

Write-Host ""
Write-Host "Done."
