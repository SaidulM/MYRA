$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".venv-build")) {
    py -m venv .venv-build
}

.\.venv-build\Scripts\python.exe -m pip install --upgrade pip
.\.venv-build\Scripts\python.exe -m pip install -r requirements-desktop.txt -r requirements-build.txt
.\.venv-build\Scripts\python.exe -m unittest discover -s tests -v
.\.venv-build\Scripts\pyinstaller.exe --clean --noconfirm packaging\MYRA.spec

Write-Host "Build output: $Root\dist\MYRA\MYRA.exe"
Write-Host "Optional installer: compile packaging\MYRA.iss with Inno Setup (ISCC.exe)."
