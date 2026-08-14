@echo off
cd /d %~dp0

if exist "client_agent.exe" (
    echo Dang khoi dong Client Agent (.exe Standalone)...
    client_agent.exe
    pause
    exit /b 0
)

if exist "dist\client_agent.exe" (
    echo Dang khoi dong Client Agent (.exe Standalone)...
    dist\client_agent.exe
    pause
    exit /b 0
)

.venv_client\Scripts\python.exe -c "import sys" >nul 2>&1
if not errorlevel 1 (
    echo Dang khoi dong Client Agent (Python script)...
    .venv_client\Scripts\python.exe client_agent.py
    pause
    exit /b 0
)

echo [LOI] Khong tim thay client_agent.exe hoac moi truong Python.
echo Hay copy file client_agent.exe hoac chay setup_client.bat truoc!
pause
