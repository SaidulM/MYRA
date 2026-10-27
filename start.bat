@echo off
REM === Stonic AI — Windows: এই ফাইলে ডবল-ক্লিক করলেই অ্যাসিস্ট্যান্ট চালু হবে ===
title Stonic AI
cd /d "%~dp0"
echo.
echo   Stonic AI চালু হচ্ছে... (বন্ধ করতে এই উইন্ডোতে Ctrl+C চাপুন)
echo.
python run.py
if errorlevel 1 (
  echo.
  echo   Python পাওয়া যায়নি! https://www.python.org থেকে ইনস্টল করুন,
  echo   ইনস্টলের সময় "Add Python to PATH" বাক্সে টিক দিন।
  pause
)
