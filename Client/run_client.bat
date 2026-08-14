@echo off
cd /d %~dp0

.venv_client\Scripts\python.exe -c "import sys" >nul 2>&1
if errorlevel 1 (
    echo [LOI] Chua cai dat hoac moi truong Client Agent bi hong. Hay chay setup_client.bat truoc!
    pause
    exit /b 1
)

echo Dang khoi dong Client Agent (Auto-Watch Mode)...
echo Nhan Ctrl+C de dung.
.venv_client\Scripts\python.exe client_agent.py
pause
