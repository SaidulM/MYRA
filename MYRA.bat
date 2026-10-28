@echo off
REM === MYRA — start (auto-updates from GitHub first, then runs). ===
REM     The Desktop / Start Menu shortcuts point here.
REM     Tip: MYRA.bat --no-update  starts instantly without checking.
title MYRA
cd /d "%~dp0"

set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY python --version >nul 2>&1 && set "PY=python"
if not defined PY goto :nopython

%PY% launcher.py %*
goto :eof

:nopython
echo.
echo   Python was not found on this laptop.
echo   Please run MYRA-Setup.bat once - it installs everything for you.
echo.
pause
