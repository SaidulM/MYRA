# =====================================================================
# MYRA — 1-Click PowerShell Desktop Installer
# Run in PowerShell:
#   irm https://raw.githubusercontent.com/SaidulM/MYRA/main/Install-MYRA.ps1 | iex
# or download and run:
#   powershell -ExecutionPolicy Bypass -File Install-MYRA.ps1
# =====================================================================
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "    🤖 MYRA — Personal Desktop AI Assistant Installer" -ForegroundColor Cyan
Write-Host "    Lightweight (<100MB) · SQLite Memory · Neural Voice" -ForegroundColor DarkCyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$InstallDir = "$env:USERPROFILE\MYRA"
$RepoUrl = "https://codeload.github.com/SaidulM/MYRA/zip/refs/heads/main"
$ZipFile = "$env:TEMP\MYRA-main.zip"
$ExtractDir = "$env:TEMP\MYRA-extract"

# Step 1: Detect Python
Write-Host "🔍 Checking Python environment..." -ForegroundColor Yellow
$PythonCmd = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    $PythonCmd = "py -3"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonCmd = "python"
}

if (-not $PythonCmd) {
    Write-Host "❌ Python 3.8+ was not found on your system." -ForegroundColor Red
    Write-Host "   Installing Python via Winget..." -ForegroundColor Yellow
    try {
        winget install -e --id Python.Python.3.11 --silent --accept-package-agreements --accept-source-agreements
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
        $PythonCmd = "python"
    } catch {
        Write-Host "   Please download Python from https://www.python.org and tick 'Add Python to PATH'." -ForegroundColor Red
        Exit 1
    }
}
Write-Host "✅ Python detected: $PythonCmd" -ForegroundColor Green

# Step 2: Download latest MYRA files
Write-Host "⬇️ Downloading MYRA release from GitHub..." -ForegroundColor Yellow
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -Uri $RepoUrl -OutFile $ZipFile -UseBasicParsing

Write-Host "📦 Extracting files into $InstallDir..." -ForegroundColor Yellow
if (Test-Path $ExtractDir) { Remove-Item -Recurse -Force $ExtractDir }
Expand-Archive -Path $ZipFile -DestinationPath $ExtractDir -Force

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
$InnerDir = Get-ChildItem -Path $ExtractDir | Where-Object { $_.PSIsContainer } | Select-Object -First 1

# Copy files preserving user .env and data
Get-ChildItem -Path $InnerDir.FullName | ForEach-Object {
    $dest = Join-Path $InstallDir $_.Name
    if ($_.Name -eq ".env" -and (Test-Path $dest)) {
        Write-Host "   Keeping existing .env keys." -ForegroundColor DarkGray
    } elseif ($_.Name -eq "data" -and (Test-Path $dest)) {
        Write-Host "   Preserving local memory database." -ForegroundColor DarkGray
    } else {
        Copy-Item -Path $_.FullName -Destination $dest -Recurse -Force
    }
}

Remove-Item -Force $ZipFile -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force $ExtractDir -ErrorAction SilentlyContinue

# Step 3: Install Edge Neural Voice Studio (edge-tts)
Write-Host "🎙️ Ensuring Neural Voice Studio engine (edge-tts)..." -ForegroundColor Yellow
try {
    & $PythonCmd -m pip install --quiet "edge-tts>=7.0.0"
    Write-Host "✅ Neural human voice engine ready." -ForegroundColor Green
} catch {
    Write-Host "ℹ️ edge-tts setup skipped (standard browser voice will be used as fallback)." -ForegroundColor DarkGray
}

# Step 4: Create Desktop & Start Menu Shortcuts
Write-Host "📌 Creating Desktop & Start Menu shortcuts..." -ForegroundColor Yellow
$WshShell = New-Object -ComObject WScript.Shell
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$StartMenuPath = [Environment]::GetFolderPath("Programs")
$BatTarget = Join-Path $InstallDir "MYRA.bat"

$Shortcut = $WshShell.CreateShortcut("$DesktopPath\MYRA.lnk")
$Shortcut.TargetPath = $BatTarget
$Shortcut.WorkingDirectory = $InstallDir
$Shortcut.Description = "MYRA — Personal Desktop AI Assistant"
$Shortcut.Save()

$MenuShortcut = $WshShell.CreateShortcut("$StartMenuPath\MYRA.lnk")
$MenuShortcut.TargetPath = $BatTarget
$MenuShortcut.WorkingDirectory = $InstallDir
$MenuShortcut.Description = "MYRA — Personal Desktop AI Assistant"
$MenuShortcut.Save()

Write-Host "✅ Shortcuts created on Desktop and Start Menu!" -ForegroundColor Green

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "🎉 Installation complete! Launching MYRA..." -ForegroundColor Green
Write-Host "   Double-click the MYRA icon on your Desktop anytime." -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

Start-Process -FilePath $BatTarget -WorkingDirectory $InstallDir
