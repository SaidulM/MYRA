@echo off
REM ============================================================
REM   🤖 MYRA — 1-Click Laptop Installer for Windows
REM   Double-click this file. It will:
REM     1) Find Python (or auto-install it via winget)
REM     2) Download and install all MYRA files from GitHub
REM     3) Put a MYRA icon on your Desktop + Start Menu
REM     4) Connect your free Gemini API key and activate MYRA
REM     5) Automatically keep MYRA updated whenever changes occur
REM ============================================================
title MYRA Installer
cd /d "%~dp0"
set "PY="

echo.
echo   ==================================================
echo     MYRA - 1-Click Desktop AI Assistant Installer
echo   ==================================================
echo.
echo   [1/3] Checking for Python...

py -3 --version >nul 2>&1 && set "PY=py -3" && goto :py_ready
python --version >nul 2>&1 && set "PY=python" && goto :py_ready

echo   Python not found - installing Python automatically via winget...
where winget >nul 2>&1 || goto :manual_py
winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements

if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe" && goto :py_ready
if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python313\python.exe" && goto :py_ready
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe" && goto :py_ready
py -3 --version >nul 2>&1 && set "PY=py -3" && goto :py_ready
goto :manual_py

:py_ready
echo   Python is ready.
echo.
echo   [2/3] Checking installer files...
if not exist "auto_setup.py" (
    echo   Downloading latest installer from GitHub...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/SaidulM/MYRA/main/auto_setup.py' -OutFile 'auto_setup.py'"
)

echo.
echo   [3/3] Running MYRA Setup...
%PY% auto_setup.py %*
echo.
pause
exit /b

:manual_py
echo.
echo   ------------------------------------------------------------
echo   Python installation needed (free, takes ~1 minute).
echo   A browser page will open now. During installation, make sure to check:
echo        [x] Add python.exe to PATH
echo   After installing Python, double-click this file again!
echo   ------------------------------------------------------------
start https://www.python.org/downloads/
echo.
pause
