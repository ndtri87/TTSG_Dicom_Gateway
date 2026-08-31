@echo off
setlocal enabledelayedexpansion
cd /d %~dp0

echo ===============================================================================
echo   CONG CU DONG GOI CLIENT AGENT MAY TRAM (STANDALONE BINARY .EXE)
echo ===============================================================================
echo.

:: 1. Kiem tra Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [LOI] Khong tim thay Python tren he thong.
    pause
    exit /b 1
)

:: 2. Kiem tra/Cai dat moi truong ao va PyInstaller
if not exist ".venv_client\Scripts\python.exe" (
    echo [*] Dang tao moi truong ao .venv_client...
    python -m venv .venv_client
)

echo [*] Dang cai dat thu vien phuc vu dong goi (pyinstaller, requests, pyyaml)...
.venv_client\Scripts\pip.exe install --upgrade pip >nul
.venv_client\Scripts\pip.exe install pyinstaller requests pyyaml >nul

if errorlevel 1 (
    echo [LOI] Cai dat thu vien that bai.
    pause
    exit /b 1
)

echo [*] Dang bien dich client_agent.py sang TTSG_ClientAgent.exe...
.venv_client\Scripts\pyinstaller.exe ^
    --onedir ^
    --name "TTSG_ClientAgent" ^
    --icon "../static/favicon.ico" ^
    --hidden-import "requests" ^
    --hidden-import "yaml" ^
    --noconfirm ^
    --clean ^
    client_agent.py

if errorlevel 1 (
    echo [LOI] Bien dich Client Agent that bai!
    pause
    exit /b 1
)

:: Copy file cau hinh mau vao thu muc dist
if exist "client_config.yaml" (
    copy /y "client_config.yaml" "dist\TTSG_ClientAgent\client_config.yaml" >nul
)

echo.
echo ===============================================================================
echo   [THANH CONG] DA TAO THANH CONG BAN RELEASE CHO CLIENT AGENT!
echo ===============================================================================
echo.
echo  Thu muc ban giao cho may tram phong kham:
echo  ==^> %CD%\dist\TTSG_ClientAgent
echo.
echo  May tram chi can sua file client_config.yaml va chay TTSG_ClientAgent.exe!
echo  Khong can cai dat bat ky moi truong Python nao!
echo ===============================================================================
echo.
pause
