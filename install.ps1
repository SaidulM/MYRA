# MYRA — 1-Line PowerShell Web Installer
# Usage in Windows PowerShell:
#   irm https://raw.githubusercontent.com/SaidulM/MYRA/main/install.ps1 | iex

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "   MYRA — 1-Click Desktop AI Assistant Installer   " -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

$tempDir = Join-Path $env:TEMP "myra-installer"
if (Test-Path $tempDir) { Remove-Item -Recurse -Force $tempDir }
New-Item -ItemType Directory -Path $tempDir | Out-Null

$installerPath = Join-Path $tempDir "auto_setup.py"
Write-Host "⬇️ Downloading installer script from GitHub..." -ForegroundColor Yellow
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/SaidulM/MYRA/main/auto_setup.py" -OutFile $installerPath

$py = "python"
try {
    & py -3 --version 2>$null
    if ($LASTEXITCODE -eq 0) { $py = "py -3" }
} catch {}

Write-Host "🚀 Launching MYRA Setup..." -ForegroundColor Green
if ($py -eq "py -3") {
    & py -3 $installerPath
} else {
    & python $installerPath
}
