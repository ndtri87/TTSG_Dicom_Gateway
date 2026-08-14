@echo off
cd /d %~dp0

if not exist ".venv\Scripts\python.exe" (
    echo [LOI] Chua cai dat. Hay chay setup.bat truoc.
    pause
    exit /b 1
)

echo Dang khoi dong RIS/Worklist gia lap (dung de test cuc bo)...
echo Nhan Ctrl+C de dung.
.venv\Scripts\python.exe mock_ris_server.py
pause
