@echo off
cd /d %~dp0

echo === Cai dat Client Agent cho May Tram Thiet Bi Y Te ===

python --version >nul 2>&1
if errorlevel 1 (
    echo [LOI] Khong tim thay Python. Hay cai Python 3.10+ tu https://www.python.org/downloads/
    echo Nho tick "Add Python to PATH" khi cai dat.
    pause
    exit /b 1
)

set VENV_OK=0
if exist ".venv_client\Scripts\python.exe" (
    .venv_client\Scripts\python.exe -c "import sys" >nul 2>&1
    if not errorlevel 1 set VENV_OK=1
)

if %VENV_OK%==0 (
    echo Dang tao moi truong ao Python cho Client Agent...
    if exist ".venv_client" rmdir /s /q .venv_client
    python -m venv .venv_client
    if errorlevel 1 (
        echo [LOI] Khong the tao moi truong ao Python.
        pause
        exit /b 1
    )
)

echo Dang cai thu vien sieu nhẹ (requests, pyyaml)...
.venv_client\Scripts\python.exe -m pip install --upgrade pip >nul
.venv_client\Scripts\python.exe -m pip install requests pyyaml

if errorlevel 1 (
    echo [LOI] Cai thu vien cho Client thất bại. xem lỗi bên trên.
    pause
    exit /b 1
)

echo.
echo === Cai dat Client Agent xong ===
echo Buoc tiep theo:
echo   1. Mo client_config.yaml, sua server_url thanh IP cua Server Gateway (Vi du: http://10.4.140.200:5000).
echo   2. Sua watch_folder thanh duong dan thu muc xuat anh cua thiet bị.
echo   3. Chay run_client.bat de bat dau theo doi xuat anh va tu dong day ve Server.
pause
