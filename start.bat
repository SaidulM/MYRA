@echo off
REM === MYRA — Windows: double-click to start ===
REM     Checks GitHub for updates, downloads them automatically,
REM     then starts MYRA (all inside MYRA.bat / launcher.py).
REM     Tip: start.bat --no-update  starts instantly, no check.
REM     First time on a new laptop? Run MYRA-Setup.bat once instead.
title MYRA
cd /d "%~dp0"
call MYRA.bat %*
