@echo off
title TikTok Link Extractor -> Excel
chcp 65001 >nul
cls

echo ============================================================
echo   TIKTOK VIDEO LINK EXTRACTOR -> EXCEL
echo ============================================================
echo.

if exist "venv\Scripts\python.exe" (
    set "PY_EXEC=venv\Scripts\python.exe"
) else (
    set "PY_EXEC=python"
)

echo [1/3] Kiem tra thu vien can thiet...
%PY_EXEC% -m pip install customtkinter playwright openpyxl

echo.
echo [2/3] Kiem tra trinh duyet Chromium...
%PY_EXEC% -m playwright install chromium

echo.
echo [3/3] Dang khoi dong Giao dien TikTok Link Extractor...
%PY_EXEC% gui.py

if %errorlevel% neq 0 (
    echo.
    echo [Loi] Chuong trinh bi dung.
    pause
)
