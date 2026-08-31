@echo off
title Cong Cu Dong Goi TTSG DICOM Gateway Server
cd /d "%~dp0"

echo ===============================================================================
echo   CONG CU DONG GOI THUONG MAI - TTSG DICOM GATEWAY SERVER
echo ===============================================================================
echo.

:: 1. Kiem tra PyInstaller trong virtualenv
if not exist ".venv\Scripts\pyinstaller.exe" (
    echo [*] Dang cai dat PyInstaller vao moi truong .venv...
    call .venv\Scripts\pip.exe install pyinstaller
)

echo [*] Bat dau tien trinh bien dich & dong goi sang ma may (PyInstaller)...
echo [*] Vui long cho trong giay lat...
echo.

:: 2. Chay PyInstaller de dong goi Server
call .venv\Scripts\pyinstaller.exe --onedir --name "TTSG_DicomGateway" --icon "static/favicon.ico" --add-data "templates;templates" --add-data "static;static" --add-data "docs/index.html;docs" --hidden-import "waitress" --hidden-import "cryptography" --hidden-import "pydicom" --hidden-import "pynetdicom" --hidden-import "watchdog" --hidden-import "pypdfium2" --hidden-import "PIL" --hidden-import "yaml" --hidden-import "sqlite3" --hidden-import "werkzeug" --hidden-import "jinja2" --hidden-import "license_manager" --hidden-import "utils" --hidden-import "dicom_builder" --hidden-import "dicom_sender" --hidden-import "retry_worker" --hidden-import "worklist_client" --hidden-import "storage_commitment_listener" --noconfirm --clean main.py

if errorlevel 1 (
    echo.
    echo [LOI] Qua trinh dong goi gap su co. Kiem tra xem co file exe nao dang chay khong.
    echo.
    pause
    exit /b 1
)

:: 3. Chuan bi thu muc phan phoi Release
set "DIST_DIR=dist\TTSG_DicomGateway"

echo.
echo [*] Dang sao chep cac file cau hinh va cong cu bo tro vao ban phat hanh...

if exist "config.yaml" copy /y "config.yaml" "%DIST_DIR%\config.yaml" >nul
if exist "TTSG_Service.exe" copy /y "TTSG_Service.exe" "%DIST_DIR%\TTSG_Service.exe" >nul
if exist "TTSG_Service.xml" copy /y "TTSG_Service.xml" "%DIST_DIR%\TTSG_Service.xml" >nul
if exist "service_install.bat" copy /y "service_install.bat" "%DIST_DIR%\service_install.bat" >nul
if exist "service_uninstall.bat" copy /y "service_uninstall.bat" "%DIST_DIR%\service_uninstall.bat" >nul

:: Loai bo triet de tat ca cac file tai lieu markdown (.md) khoi ban phat hanh
if exist "%DIST_DIR%\*.md" del /f /q "%DIST_DIR%\*.md" >nul 2>&1
if exist "%DIST_DIR%\docs\*.md" del /f /q "%DIST_DIR%\docs\*.md" >nul 2>&1
if exist "%DIST_DIR%\_internal\docs\*.md" del /f /q "%DIST_DIR%\_internal\docs\*.md" >nul 2>&1

echo @echo off > "%DIST_DIR%\run_server.bat"
echo title TTSG DICOM Gateway Server >> "%DIST_DIR%\run_server.bat"
echo cd /d "%%~dp0" >> "%DIST_DIR%\run_server.bat"
echo TTSG_DicomGateway.exe >> "%DIST_DIR%\run_server.bat"
echo pause >> "%DIST_DIR%\run_server.bat"

echo.
echo ===============================================================================
echo   [THANH CONG] DA DONG GOI BAN PHAT HANH THUONG MAI THANH CONG!
echo ===============================================================================
echo.
echo  File chay chinh:
echo  ==^> %CD%\%DIST_DIR%\TTSG_DicomGateway.exe
echo.
echo ===============================================================================
echo.

if exist "%DIST_DIR%\TTSG_DicomGateway.exe" explorer.exe /select,"%CD%\%DIST_DIR%\TTSG_DicomGateway.exe"

pause
