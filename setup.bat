@echo off
cd /d %~dp0

echo === Cai dat DICOM Gateway Service ===

python --version >nul 2>&1
if errorlevel 1 (
    echo [LOI] Khong tim thay Python. Hay cai Python 3.10+ tu https://www.python.org/downloads/
    echo Nho tick "Add Python to PATH" khi cai dat.
    pause
    exit /b 1
)

set VENV_OK=0
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe -c "import sys" >nul 2>&1
    if not errorlevel 1 set VENV_OK=1
)

if %VENV_OK%==0 (
    echo Dang tao moi truong ao Python...
    if exist ".venv" rmdir /s /q .venv
    python -m venv .venv
    if errorlevel 1 (
        echo [LOI] Khong the tao moi truong ao Python.
        pause
        exit /b 1
    )
)

echo Dang cai thu vien...
.venv\Scripts\python.exe -m pip install --upgrade pip >nul
.venv\Scripts\python.exe -m pip install -r requirements.txt

if errorlevel 1 (
    echo [LOI] Cai thu vien that bai. Xem loi ben tren.
    pause
    exit /b 1
)

echo.
echo === Cai dat xong ===
echo Buoc tiep theo:
echo   1. Mo config.yaml, sua IP/Port/AE Title cua PACS that va duong dan thu muc theo doi.
echo   2. Chay test_ket_noi_pacs.bat de kiem tra ket noi PACS.
echo   3. Chay run.bat de khoi dong service.
pause
