@echo off
REM === MYRA — 100% Native Python Desktop GUI Window ===
REM     Runs the standalone Python desktop application directly.
REM     Zero browser, zero tabs, pure desktop software experience.
title MYRA Desktop AI Assistant
cd /d "%~dp0"

set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY python --version >nul 2>&1 && set "PY=python"
if not defined PY goto :nopython

echo Starting MYRA Native Desktop Application...
%PY% myra_gui.py %*
goto :eof

:nopython
echo.
echo   Python was not found on this laptop.
echo   Please run MYRA-Setup.bat once - it installs everything for you.
echo.
pause
