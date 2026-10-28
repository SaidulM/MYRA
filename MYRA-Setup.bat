@echo off
REM ============================================================
REM   MYRA - ONE-TIME SETUP for Windows
REM   Double-click this file ONCE. It will:
REM     1) Find Python (or install it automatically with winget)
REM     2) Install MYRA to C:\Users\<you>\MYRA
REM     3) Put a MYRA icon on your Desktop + Start Menu
REM   After that, just double-click the MYRA icon every day -
REM   updates download automatically at every start.
REM ============================================================
title MYRA Setup
cd /d "%~dp0"
set "PY="

echo.
echo   MYRA setup - checking for Python...

py -3 --version >nul 2>&1 && set "PY=py -3" && goto :found
python --version >nul 2>&1 && set "PY=python" && goto :found

echo   Python not found - trying to install it automatically...
where winget >nul 2>&1 || goto :manual
winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements

if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe" && goto :found
if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python313\python.exe" && goto :found
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe" && goto :found
py -3 --version >nul 2>&1 && set "PY=py -3" && goto :found
goto :manual

:found
echo   Python ready. Running the MYRA installer...
echo.
%PY% auto_setup.py
echo.
pause
exit /b

:manual
echo.
echo   ------------------------------------------------------------
echo   One manual step is needed: install Python (free, 2 minutes).
echo   A download page will open now. During installation, tick:
echo        [x] Add python.exe to PATH
echo   Then double-click MYRA-Setup.bat again - it does the rest.
echo   ------------------------------------------------------------
start https://www.python.org/downloads/
echo.
pause
