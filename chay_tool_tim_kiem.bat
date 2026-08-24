@echo off
title TikTok Real Video Search & Excel Exporter
chcp 65001 >nul
cls
echo ============================================================
echo   TIKTOK REAL VIDEO SEARCH & EXCEL EXPORTER
echo ============================================================
echo.

if exist "venv\Scripts\python.exe" (
    set "PY_EXEC=venv\Scripts\python.exe"
) else (
    set "PY_EXEC=python"
)

echo [1/3] Kiem tra thu vien Playwright va Openpyxl...
%PY_EXEC% -c "import playwright, openpyxl" >nul 2>&1
if %errorlevel% neq 0 (
    echo Dang cai dat playwright va openpyxl...
    %PY_EXEC% -m pip install playwright openpyxl
)

echo.
echo [2/3] Kiem tra trinh duyet Chromium...
%PY_EXEC% -m playwright install chromium

echo.
echo [3/3] Dang khoi dong Giao dien UI...
%PY_EXEC% tiktok_search_gui.py

if %errorlevel% neq 0 (
    echo.
    echo [Loi] Chuong trinh bi dung.
    pause
)
