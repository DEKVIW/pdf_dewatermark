# Interactive first-time open-source setup:
#   git init, remote, optional gh repo create, first commit guidance.
# Does NOT force-push. Push only after your confirmation.
#
# NOTE: Avoid Chinese string literals in this .ps1 when possible (PS 5.1 encoding).
# Usage:
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

function Invoke-Git {
    # Run git without turning stderr into terminating errors under $ErrorActionPreference Stop
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$GitArgs)
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & git @GitArgs 2>&1 | ForEach-Object { "$_" }
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $old
    }
}

function Get-GitRemoteUrl([string]$Name = "origin") {
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $out = & git remote get-url $Name 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) {
            return ([string]$out).Trim()
        }
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

Write-Host "JingYe - open source init (interactive)"
Write-Host "Root: $Root"

# --- Git available? ---
Write-Step "Check Git"
$oldEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$gitVer = & git --version 2>&1
$ErrorActionPreference = $oldEap
if ($LASTEXITCODE -ne 0) {
    Write-Error "Git not found. Install Git for Windows: https://git-scm.com/"
}
Write-Host $gitVer

# --- git init ---
Write-Step "Repository"
if (-not (Test-Path (Join-Path $Root ".git"))) {
    if (Ask-YesNo "No .git found. Run git init here?") {
        Invoke-Git init | Out-Host
        Invoke-Git branch -M main | Out-Null
        Write-Host "Initialized empty repo (branch main if supported)."
    } else {
        Write-Host "Skipped git init. Exit."
        exit 0
    }
} else {
    Write-Host "Already a git repository."
}

# --- identity hint ---
$userName = Get-GitConfig "user.name"
$userEmail = Get-GitConfig "user.email"
if (-not $userName -or -not $userEmail) {
    Write-Host "Git user.name / user.email not set."
    Write-Host "Example:"
    Write-Host '  git config --global user.name "YourName"'
    Write-Host '  git config --global user.email "you@example.com"'
    if (Ask-YesNo "Set local user.name/email for this repo now?" $false) {
        $n = Read-Host "user.name"
        $e = Read-Host "user.email"
        if ($n) { git config user.name $n }
        if ($e) { git config user.email $e }
    }
}

# --- ignore check ---
Write-Step "Sanity check (.gitignore)"
if (-not (Test-Path ".gitignore")) {
    Write-Warning ".gitignore missing!"
} else {
    Write-Host ".gitignore present."
}

$danger = @()
if (Test-Path "dist") { $danger += "dist/ (should be ignored, not committed)" }
if (Test-Path ".venv") { $danger += ".venv/ (should be ignored)" }
if (Test-Path "data/gui_prefs.json") { $danger += "data/gui_prefs.json (ignored)" }
$pdfs = Get-ChildItem -Recurse -File -Filter "*.pdf" -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch "\\tests\\fixtures\\" } |
    Select-Object -First 5
if ($pdfs) {
    $danger += ("sample PDFs under project (ignored by *.pdf): {0} ..." -f $pdfs[0].Name)
}
if ($danger.Count -gt 0) {
    Write-Host "Local items that must NOT be force-added:"
    $danger | ForEach-Object { Write-Host "  - $_" }
} else {
    Write-Host "No obvious danger paths found."
}

# --- remote ---
Write-Step "Configure remote origin"
$existing = Get-GitRemoteUrl "origin"
if ($existing) {
    Write-Host "Current origin: $existing"
    if (-not (Ask-YesNo "Keep this remote?" $true)) {
        Invoke-Git remote remove origin | Out-Null
        $existing = $null
        Write-Host "Removed origin."
    }
}

if (-not $existing) {
    Write-Host ""
    Write-Host "You need a GitHub repository URL, for example:"
    Write-Host "  https://github.com/YOUR_USER/JingYe.git"
    Write-Host "  git@github.com:YOUR_USER/JingYe.git"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  1) Paste URL of an empty repo you already created on github.com"
    Write-Host "  2) Use GitHub CLI (gh) to create a new public repo (if installed)"
    Write-Host "  3) Skip remote for now"
    $choice = Read-Host "Choose 1/2/3"
    switch ($choice) {
        "1" {
            $url = Read-Host "Remote URL"
            if ($url) {
                $url = $url.Trim()
                Invoke-Git remote add origin $url | Out-Host
                if ($LASTEXITCODE -eq 0) {
                    Write-Host "Added origin -> $url"
                } else {
                    Write-Warning "git remote add failed."
                }
            }
        }
        "2" {
            $gh = Get-Command gh -ErrorAction SilentlyContinue
            if (-not $gh) {
                Write-Warning "gh not found. Install: https://cli.github.com/ then: gh auth login"
                Write-Host "Falling back: paste URL instead."
                $url = Read-Host "Remote URL"
                if ($url) {
                    Invoke-Git remote add origin $url.Trim() | Out-Host
                }
            } else {
                Write-Host "gh found: $((gh --version | Select-Object -First 1))"
                $repoName = Read-Host "New repo name (e.g. JingYe or pdf-dewatermark)"
                if (-not $repoName) { $repoName = "JingYe" }
                $vis = Read-Host "Visibility public/private [public]"
                if ([string]::IsNullOrWhiteSpace($vis)) { $vis = "public" }
                $visFlag = if ($vis -match "priv") { "--private" } else { "--public" }
                Write-Host "Creating github.com repo: $repoName ($visFlag) ..."
                $oldEap = $ErrorActionPreference
                $ErrorActionPreference = "Continue"
                & gh repo create $repoName $visFlag --source=. --remote=origin --description "JingYe PDF color cleanup tool"
                $ghCode = $LASTEXITCODE
                $ErrorActionPreference = $oldEap
                if ($ghCode -ne 0) {
                    Write-Warning "gh repo create failed. Create the repo on the website and re-run, choose option 1."
                } else {
                    Write-Host "Remote origin configured by gh."
                }
            }
        }
        default {
            Write-Host "Skipped remote. You can later:"
            Write-Host "  git remote add origin https://github.com/USER/REPO.git"
        }
    }
}

# --- status / first commit ---
Write-Step "Working tree"
Invoke-Git status -sb | Out-Host
Write-Host ""
Write-Host "Suggested first commit (review carefully):"
Write-Host "  git add .gitignore LICENSE README.md pyproject.toml requirements.txt"
Write-Host "  git add src tests docs legacy packaging scripts run_gui.bat"
Write-Host "  git add logs/.gitkeep output/.gitkeep"
Write-Host "  git status   # confirm NO dist/, .venv/, user PDFs"
Write-Host '  git commit -m "chore: initial open source release"'
Write-Host ""

if (Ask-YesNo "Run a safe git add for common source paths now?" $true) {
    $oldEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    git add -- ".gitignore" "LICENSE" "README.md" "pyproject.toml" "requirements.txt" "run_gui.bat" 2>$null
    git add -- "src" "tests" "docs" "legacy" "packaging" "scripts" 2>$null
    git add -- "logs/.gitkeep" "output/.gitkeep" 2>$null
    $ErrorActionPreference = $oldEap
    Write-Host "Staged. Review:"
    Invoke-Git status | Out-Host
    Write-Host ""
    if (Ask-YesNo "Create initial commit now?" $true) {
        $oldEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        git commit -m "chore: initial open source (JingYe)"
        $c = $LASTEXITCODE
        $ErrorActionPreference = $oldEap
        if ($c -ne 0) {
            Write-Warning "Commit failed (nothing staged or identity missing)."
        }
    }
}

$originNow = Get-GitRemoteUrl "origin"
if ($originNow) {
    Write-Step "Push"
    Write-Host "Remote: $originNow"
    Write-Host "This will run: git push -u origin <current-branch>"
    if (Ask-YesNo "Push to origin now?" $false) {
        $oldEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        $branch = (& git rev-parse --abbrev-ref HEAD 2>$null)
        if (-not $branch) { $branch = "main" }
        $branch = $branch.Trim()
        git push -u origin $branch
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Push failed. Check auth (HTTPS token / SSH key) and branch name."
            Write-Host "GitHub HTTPS: use Personal Access Token as password, or use SSH."
        }
        $ErrorActionPreference = $oldEap
    } else {
        Write-Host "Skipped push. When ready:"
        Write-Host "  git push -u origin main"
    }
} else {
    Write-Host ""
    Write-Host "No origin remote. After you create a GitHub repo:"
    Write-Host "  git remote add origin https://github.com/USER/REPO.git"
    Write-Host "  git push -u origin main"
}

Write-Step "Next"
Write-Host "Build + publish zip to GitHub Releases:"
Write-Host "  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\release.ps1"
Write-Host "Done."
