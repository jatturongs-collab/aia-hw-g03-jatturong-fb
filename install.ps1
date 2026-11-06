# One-time installer for Windows 11 / PowerShell. No admin rights needed.
# Run:  powershell -ExecutionPolicy Bypass -File .\install.ps1
# For academic study only - see DISCLAIMER.md
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Set-Location $PSScriptRoot

# Files from a GitHub "Download ZIP" carry a "downloaded from the internet" mark, and PowerShell
# then refuses to run .\run.ps1 ("is not digitally signed"). Remove the mark from this folder only.
Get-ChildItem -Path $PSScriptRoot -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch '\\\.venv\\' } |
    Unblock-File -ErrorAction SilentlyContinue

Write-Host "== 1/4 Checking Python ==" -ForegroundColor Cyan
$py = $null
$ver = ""
foreach ($c in @("py -3", "python")) {
    try {
        $ver = (Invoke-Expression "$c --version" 2>$null) | Out-String
        if ($ver -match "Python 3\.(\d+)" -and [int]$Matches[1] -ge 10) { $py = $c; break }
    } catch {}
}
if (-not $py) {
    Write-Host "Python 3.10+ not found." -ForegroundColor Yellow
    Write-Host "Install it with:  winget install Python.Python.3.12"
    Write-Host "or download from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), then run this script again."
    exit 1
}
Write-Host "Using: $py ($($ver.Trim()))"

Write-Host "== 2/4 Creating private Python environment (.venv) ==" -ForegroundColor Cyan
if (-not (Test-Path ".venv\Scripts\python.exe")) { Invoke-Expression "$py -m venv .venv" }
$vpy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
& $vpy -m pip install --upgrade pip --quiet
& $vpy -m pip install -r requirements.txt --quiet
if ($LASTEXITCODE -ne 0) { Write-Host "pip install failed." -ForegroundColor Red; exit 1 }

Write-Host "== 3/4 Checking browser ==" -ForegroundColor Cyan
$chrome = @("$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
            "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
            "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe") |
          Where-Object { Test-Path $_ } | Select-Object -First 1
if ($chrome) {
    Write-Host "Google Chrome found - it will be used."
} else {
    Write-Host "Google Chrome not found - downloading Playwright Chromium (about 150 MB)..."
    & $vpy -m playwright install chromium
}

Write-Host "== 4/4 Done ==" -ForegroundColor Green
Write-Host @"

Next steps (in this same PowerShell window):
  1. .\run.ps1 test                      # optional self-test on a fake page (no Facebook)
  2. .\run.ps1 login                     # a browser opens: log in to YOUR OWN account, then press ENTER here
  3. .\run.ps1 scrape -Url https://www.facebook.com/WriterTable -Max 20

Results appear in the 'report' folder. Read DISCLAIMER.md first: academic study only.
"@
