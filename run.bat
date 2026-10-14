@echo off
cd /d %~dp0

.venv\Scripts\python.exe -c "import sys" >nul 2>&1
if errorlevel 1 (
    echo [LOI] Chua cai dat hoac moi truong virtualenv bi hong. Hay chay setup.bat truoc!
    pause
    exit /b 1
)

echo Dang khoi dong DICOM Gateway Service...
echo Nhan Ctrl+C de dung.
.venv\Scripts\python.exe main.py
pause
