@echo off
REM ASCII-only .bat (avoid cmd GBK mis-parsing UTF-8 Chinese).
cd /d "%~dp0"
title JingYe
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

if exist ".venv\Scripts\pythonw.exe" (
  REM Empty title "" so start does not swallow the exe path; /D sets cwd.
  start "" /D "%~dp0" ".venv\Scripts\pythonw.exe" -m pdf_dewatermark
  exit /b 0
)
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m pdf_dewatermark
  exit /b %ERRORLEVEL%
)
where pythonw >nul 2>&1 && (
  start "" /D "%~dp0" pythonw -m pdf_dewatermark
  exit /b 0
)
python -m pdf_dewatermark
