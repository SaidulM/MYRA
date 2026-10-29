# Compatibility shim only. The supported builder is pure Python:
#   py packaging\build_windows.py
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
py packaging\build_windows.py @args
