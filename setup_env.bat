@echo off
title TOLLCAL - Setup Environment
echo ============================================================
echo   DANG KHOI TAO VENV VA CAI DAT THU VIEN CHO TOLLCAL
echo ============================================================
echo.

if not exist "venv\Scripts\python.exe" (
    echo [*] Dang tao moi truong ao venv...
    python -m venv venv
) else (
    echo [*] Moi truong venv da ton tai.
)

echo [*] Dang nang cap pip va cai dat cac thu vien tu requirements.txt...
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt

echo.
echo ============================================================
echo   CAI DAT HOAN TAT 100%!
echo   Ban co the nhap dup chuot vao file 'run_ui.bat' de mo web.
echo ============================================================
pause
