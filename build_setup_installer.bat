@echo off
title Dong Goi Bo Cai Dat Setup.exe - TTSG DICOM Gateway
cd /d "%~dp0"

echo ===============================================================================
echo   DONG GOI BO CAI DAT CHUYEN NGHIEP (SETUP.EXE) - TTSG DICOM GATEWAY
echo ===============================================================================
echo.

set ISCC_PATH=
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC_PATH=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if exist "C:\Users\UTKEN\AppData\Local\Programs\Inno Setup 6\ISCC.exe" set "ISCC_PATH=C:\Users\UTKEN\AppData\Local\Programs\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC_PATH=C:\Program Files\Inno Setup 6\ISCC.exe"

if defined ISCC_PATH goto ISCC_FOUND

echo [LOI] Khong tim thay Inno Setup Compiler.
echo Vui long cai dat Inno Setup 6.
echo.
pause
exit /b 1

:ISCC_FOUND
echo [*] Trinh bien dich Inno Setup: "%ISCC_PATH%"
echo.

echo ===============================================================================
echo [BUOC 1/2] BIEN DICH MA NGUON SANG MA MAY (PYINSTALLER)
echo ===============================================================================
echo.

if not exist ".venv\Scripts\pyinstaller.exe" (
    echo [*] Dang cai dat PyInstaller vao moi truong .venv...
    call .venv\Scripts\pip.exe install pyinstaller
)

echo [*] Dang dong goi TTSG_DicomGateway.exe (vui long cho trong giay lat)...
call .venv\Scripts\pyinstaller.exe --onedir --name "TTSG_DicomGateway" --icon "static/favicon.ico" --add-data "templates;templates" --add-data "static;static" --add-data "docs/index.html;docs" --hidden-import "waitress" --hidden-import "cryptography" --hidden-import "pydicom" --hidden-import "pynetdicom" --hidden-import "watchdog" --hidden-import "pypdfium2" --hidden-import "PIL" --hidden-import "yaml" --hidden-import "sqlite3" --hidden-import "werkzeug" --hidden-import "jinja2" --hidden-import "license_manager" --hidden-import "utils" --hidden-import "dicom_builder" --hidden-import "dicom_sender" --hidden-import "retry_worker" --hidden-import "worklist_client" --hidden-import "storage_commitment_listener" --noconfirm --clean main.py

if errorlevel 1 goto BUILD_ERROR

set "DIST_DIR=dist\TTSG_DicomGateway"
echo.
echo [*] Dang chuan bi cac file phu tro (Service Wrapper, config, scripts)...
if exist "config.yaml" copy /y "config.yaml" "%DIST_DIR%\config.yaml" >nul
if exist "TTSG_Service.exe" copy /y "TTSG_Service.exe" "%DIST_DIR%\TTSG_Service.exe" >nul
if exist "TTSG_Service.xml" copy /y "TTSG_Service.xml" "%DIST_DIR%\TTSG_Service.xml" >nul
if exist "service_install.bat" copy /y "service_install.bat" "%DIST_DIR%\service_install.bat" >nul
if exist "service_uninstall.bat" copy /y "service_uninstall.bat" "%DIST_DIR%\service_uninstall.bat" >nul

:: Loai bo triet de tat ca cac file tai lieu markdown (.md) khoi ban phat hanh thuong mai
if exist "%DIST_DIR%\*.md" del /f /q "%DIST_DIR%\*.md" >nul 2>&1
if exist "%DIST_DIR%\docs\*.md" del /f /q "%DIST_DIR%\docs\*.md" >nul 2>&1
if exist "%DIST_DIR%\_internal\docs\*.md" del /f /q "%DIST_DIR%\_internal\docs\*.md" >nul 2>&1

echo @echo off > "%DIST_DIR%\run_server.bat"
echo title TTSG DICOM Gateway Server >> "%DIST_DIR%\run_server.bat"
echo cd /d "%%~dp0" >> "%DIST_DIR%\run_server.bat"
echo TTSG_DicomGateway.exe >> "%DIST_DIR%\run_server.bat"
echo pause >> "%DIST_DIR%\run_server.bat"

echo [OK] Hoan thanh Buoc 1: Thu muc phan phoi da san sang (Da loai bo toan bo file .md).
echo.

echo ===============================================================================
echo [BUOC 2/2] BIEN DICH FILE CAI DAT SETUP.EXE (INNO SETUP)
echo ===============================================================================
echo.
echo [*] Dang tao file TTSG_DicomGateway_Setup_v2.0.exe...
"%ISCC_PATH%" installer.iss

if errorlevel 1 goto INNO_ERROR

echo.
echo ===============================================================================
echo   [THANH CONG] DA TAO BO CAI DAT CHUYEN NGHIEP THANH CONG!
echo ===============================================================================
echo.
echo  File cai dat Setup 1-Click:
echo  ==^> %CD%\dist\TTSG_DicomGateway_Setup_v2.0.exe
echo.
echo ===============================================================================
echo.

if exist "dist\TTSG_DicomGateway_Setup_v2.0.exe" explorer.exe /select,"%CD%\dist\TTSG_DicomGateway_Setup_v2.0.exe"

pause
exit /b 0

:BUILD_ERROR
echo.
echo [LOI] Bien dich PyInstaller that bai. Vui long kiem tra lai.
echo.
pause
exit /b 1

:INNO_ERROR
echo.
echo [LOI] Bien dich Inno Setup that bai.
echo.
pause
exit /b 1
