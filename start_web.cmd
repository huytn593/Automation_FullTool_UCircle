@echo off
cmd /k "python --version 2>nul && (python -m venv venv 2>nul & venv\Scripts\python.exe -m pip install -r requirements.txt & venv\Scripts\python.exe main.py ui) || (py -m venv venv 2>nul & venv\Scripts\python.exe -m pip install -r requirements.txt & venv\Scripts\python.exe main.py ui) || echo [LOI] Vui long kiem tra Python da cai dat chua."
