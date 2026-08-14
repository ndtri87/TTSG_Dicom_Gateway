@echo off
cd /d %~dp0

if not exist ".venv\Scripts\python.exe" (
    echo [LOI] Chua cai dat. Hay chay setup.bat truoc.
    pause
    exit /b 1
)

echo Dang khoi dong PACS gia lap (dung de test cuc bo)...
echo File nhan duoc se luu vao .\data\mock_pacs_received
echo Nhan Ctrl+C de dung.
.venv\Scripts\python.exe mock_pacs_server.py
pause
