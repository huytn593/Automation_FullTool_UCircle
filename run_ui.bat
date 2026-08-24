@echo off
title TOLLCAL Web UI
chcp 65001 >nul
cls
echo ============================================================
echo   TOLLCAL: HE THONG DONG BO TIKTOK SANG UCIRCLE WAVEE
echo ============================================================
echo.

:: 1. Kiem tra Python
if exist "venv\Scripts\python.exe" (
    set "PY_CMD=venv\Scripts\python.exe"
) else (
    set "PY_CMD=python"
)

:: 2. Giai phong cong 8000 neu bi chiem boi tien trinh cu
echo [1/3] Kiem tra va giai phong cong 8000 neu co tien trinh chay ngam...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do (
    echo Dang dong tien trinh cu PID %%a tren cong 8000...
    taskkill /f /pid %%a >nul 2>&1
)

:: 3. Kiem tra va khoi chay Web Server
echo.
echo [2/3] Dang khoi chay Giao dien Web tai: http://127.0.0.1:8000
echo (Nhan Ctrl+C tren cua so nay de tat may chu)
echo.

%PY_CMD% main.py ui

if %errorlevel% neq 0 (
    echo.
    echo ============================================================
    echo [THONG BAO] Neu ban muon dung Tool Tim Kiem Video TikTok va Xuat Excel:
    echo Hay chay file: chay_tool_tim_kiem.bat
    echo Hoac go lenh: python main.py search "tu khoa" --output ket_qua.xlsx
    echo ============================================================
    pause
)
