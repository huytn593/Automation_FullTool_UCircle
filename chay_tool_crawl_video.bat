@echo off
title TikTok Video Link Crawler - TOLLCAL
chcp 65001 >nul
cls

echo ============================================================
echo   TOOL CRAWL LINK VIDEO TIKTOK - XUAT EXCEL FORMAT |link|
echo ============================================================
echo.

if exist "venv\Scripts\python.exe" (
    set "PY_EXEC=venv\Scripts\python.exe"
) else (
    set "PY_EXEC=python"
)

echo [1/2] Kiem tra moi truong va thu vien...
%PY_EXEC% -m pip install -r requirements.txt >nul 2>&1

echo [2/2] Dang khoi dong Giao dien Crawl Link Video...
%PY_EXEC% gui.py

if %errorlevel% neq 0 (
    echo.
    echo [Loi] Chuong trinh bi dung.
    pause
)
