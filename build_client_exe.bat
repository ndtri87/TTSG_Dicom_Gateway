@echo off
cd /d %~dp0

echo === Dong goi Client Agent thanh file client_agent.exe doc lap ===

.venv\Scripts\python.exe -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo Dang cai pyinstaller...
    .venv\Scripts\python.exe -m pip install pyinstaller
)

echo Dang dong goi...
.venv\Scripts\pyinstaller.exe --onefile --name client_agent client_agent.py

if errorlevel 1 (
    echo [LOI] Dong goi that bai. xem loi ben tren.
    pause
    exit /b 1
)

echo.
echo === DONG GOI THANH CONG! ===
echo File client_agent.exe nam tai thu muc: dist\client_agent.exe
echo Ban chi cun copy file dist\client_agent.exe va client_config.yaml sang may Client bat ky de chay ngay (Khong can cai Python).
pause
