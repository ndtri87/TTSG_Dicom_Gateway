@echo off
cd /d %~dp0

if not exist ".venv\Scripts\python.exe" (
    echo [LOI] Chua cai dat. Hay chay setup.bat truoc.
    pause
    exit /b 1
)

.venv\Scripts\python.exe test_pacs_connection.py
pause
