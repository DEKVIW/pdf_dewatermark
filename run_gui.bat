@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 净页 JingYe
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m pdf_dewatermark
) else (
  python -m pdf_dewatermark
)
