@echo off
REM === MYRA — Windows: double-click this file to start the assistant ===
title MYRA
cd /d "%~dp0"
echo.
echo   Starting MYRA... (press Ctrl+C in this window to quit)
echo.
python run.py
if errorlevel 1 (
  echo.
  echo   Python was not found! Install it from https://www.python.org
  echo   and tick "Add Python to PATH" during installation.
  pause
)
