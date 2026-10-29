@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title MYRA Desktop (source test build)

if not exist ".venv-desktop\Scripts\python.exe" (
  echo.
  echo MYRA native desktop first-time setup
  echo This downloads PySide6 and keyring once from PyPI. Later starts reuse them.
  echo.
  where py >nul 2>nul
  if !errorlevel!==0 (
    py -m venv .venv-desktop
  ) else (
    python -m venv .venv-desktop
  )
  if not exist ".venv-desktop\Scripts\python.exe" (
    echo Python could not create the desktop environment.
    pause
    exit /b 1
  )
  ".venv-desktop\Scripts\python.exe" -m pip install --upgrade pip
  ".venv-desktop\Scripts\python.exe" -m pip install -r requirements-desktop.txt
  if !errorlevel! neq 0 (
    echo Desktop dependency install failed. Check the internet connection and try again.
    pause
    exit /b 1
  )
)

".venv-desktop\Scripts\python.exe" run_desktop.py
if !errorlevel! neq 0 pause
