# Friendly wrapper around the Python scripts. Run  .\run.ps1 help  for usage.
# For academic study only - see DISCLAIMER.md
param(
    [Parameter(Position = 0)][string]$Command = "help",
    [string]$Url = "https://www.facebook.com/WriterTable",
    [int]$Max = 0,              # 0 = no limit
    [int]$Target = 500,         # for scrape-until
    [int]$Year = 0,
    [string]$Keywords = "",
    [string]$TagsFile = "",
    [switch]$Headless,
    [switch]$PhotosOnly,
    [switch]$NoImages,
    [string]$Output = "report\All_Post.md"
)
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"
Set-Location $PSScriptRoot
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if ($Command -ne "help" -and -not (Test-Path $py)) {
    Write-Host "Not installed yet. Run:  powershell -ExecutionPolicy Bypass -File .\install.ps1" -ForegroundColor Yellow
    exit 1
}

function Get-ExtraArgs {
    $a = @()
    if ($Keywords)   { $a += @("--keywords", $Keywords) }
    if ($TagsFile)   { $a += @("--tags-file", $TagsFile) }
    if ($Year -gt 0) { $a += @("--year", "$Year") }
    if ($Headless)   { $a += "--headless" }
    if ($PhotosOnly) { $a += "--photos-only" }
    if ($NoImages)   { $a += "--no-download-images" }
    return $a
}

switch ($Command) {
    "login" {
        Write-Host "A browser window opens. Log in to your OWN Facebook account (incl. 2FA), then press ENTER here." -ForegroundColor Cyan
        & $py extract_posts.py --login
    }
    "login-chrome" {
        # Log in with a NORMAL Chrome window (no automation attached) that uses the same profile folder
        # the scraper uses later. Use this if "login" hangs or Facebook says the login is incorrect.
        $chrome = @("$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
                    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
                    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe") |
                  Where-Object { Test-Path $_ } | Select-Object -First 1
        if (-not $chrome) { Write-Host "Google Chrome not found. Install Chrome, or use: .\run.ps1 login" -ForegroundColor Yellow; exit 1 }
        $profileDir = Join-Path $env:LOCALAPPDATA "fb-post-extractor\profile"
        New-Item -ItemType Directory -Force $profileDir | Out-Null
        Write-Host "A normal Chrome window opens. Log in to your OWN Facebook account, wait until you see your News Feed," -ForegroundColor Cyan
        Write-Host "then CLOSE that Chrome window completely, and press ENTER here." -ForegroundColor Cyan
        Start-Process -FilePath $chrome -ArgumentList @("--user-data-dir=`"$profileDir`"", "--no-first-run", "--no-default-browser-check", "https://www.facebook.com/")
        Read-Host "Press ENTER after you closed Chrome"
        Write-Host "Session saved in $profileDir. Next: .\run.ps1 scrape -Max 5" -ForegroundColor Green
    }
    "scrape" {
        $a = @("--url", $Url, "--output", $Output) + (Get-ExtraArgs)
        if ($Max -gt 0) { $a += @("--max-posts", "$Max") }
        & $py extract_posts.py @a
        if ($LASTEXITCODE -eq 3) { Write-Host "Login needed. Run:  .\run.ps1 login" -ForegroundColor Yellow }
    }
    "scrape-until" {
        $a = @("--target", "$Target", "--", "--url", $Url, "--output", $Output) + (Get-ExtraArgs)
        & $py run_until.py @a
    }
    "test" {
        & $py test\mock_fb.py --headless
        Write-Host "--- year filter on the mock page (expect only 2025/2024 posts) ---"
        & $py test\mock_fb.py --headless --year 2025 --output test\out_year\All_Post.md
    }
    default {
        Write-Host @"
Usage:  .\run.ps1 <command> [options]

  login          open browser, log in once (your own account), press ENTER
  login-chrome   same, but in a normal Chrome window (use this if "login" hangs or says incorrect)
  scrape         collect posts into report\All_Post.md
  scrape-until   repeat runs with cool-downs until -Target posts
  test           self-test against a fake page (no Facebook, no login)

Options:  -Url <page>  -Max <n>  -Target <n>  -Year <yyyy>  -Keywords "a,b"  -TagsFile tags.txt
          -Headless  -PhotosOnly  -NoImages  -Output <file.md>
Example:  .\run.ps1 scrape -Url https://www.facebook.com/WriterTable -Max 20
Academic study only - read DISCLAIMER.md.
"@
    }
}
