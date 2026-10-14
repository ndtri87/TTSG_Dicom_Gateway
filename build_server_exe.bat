@echo off
title Cong Cu Dong Goi TTSG DICOM Gateway Server
cd /d "%~dp0"

:: Tham so "nopause": duoc goi tu build_setup_installer.bat, khong dung man hinh / mo Explorer
set "NOPAUSE=%~1"

echo ===============================================================================
echo   CONG CU DONG GOI THUONG MAI - TTSG DICOM GATEWAY SERVER
echo ===============================================================================
echo.

:: 1. Kiem tra PyInstaller trong virtualenv
if not exist ".venv\Scripts\pyinstaller.exe" (
    echo [*] Dang cai dat PyInstaller vao moi truong .venv...
    call .venv\Scripts\pip.exe install pyinstaller
)

echo [*] Bat dau bien dich theo TTSG_DicomGateway.spec (PyInstaller)...
echo.

:: 2. Toan bo cau hinh build (hidden imports, datas, excludes) nam trong file .spec
call .venv\Scripts\pyinstaller.exe TTSG_DicomGateway.spec --noconfirm --clean
if errorlevel 1 goto BUILD_ERROR

:: 3. Chuan bi thu muc phan phoi Release
set "DIST_DIR=dist\TTSG_DicomGateway"

echo.
echo [*] Dang sao chep cac file cau hinh va cong cu bo tro vao ban phat hanh...

:: Ban phat hanh dung cau hinh mau SACH (khong tai khoan/mat khau), khong dung config.yaml cua may dev
copy /y "config.default.yaml" "%DIST_DIR%\config.yaml" >nul
if errorlevel 1 goto BUILD_ERROR
if exist "TTSG_Service.exe" copy /y "TTSG_Service.exe" "%DIST_DIR%\TTSG_Service.exe" >nul
if exist "TTSG_Service.xml" copy /y "TTSG_Service.xml" "%DIST_DIR%\TTSG_Service.xml" >nul
if exist "service_install.bat" copy /y "service_install.bat" "%DIST_DIR%\service_install.bat" >nul
if exist "service_uninstall.bat" copy /y "service_uninstall.bat" "%DIST_DIR%\service_uninstall.bat" >nul

:: Loai bo tat ca file tai lieu markdown (.md) khoi ban phat hanh
if exist "%DIST_DIR%\*.md" del /f /q "%DIST_DIR%\*.md" >nul 2>&1
if exist "%DIST_DIR%\docs\*.md" del /f /q "%DIST_DIR%\docs\*.md" >nul 2>&1
if exist "%DIST_DIR%\_internal\docs\*.md" del /f /q "%DIST_DIR%\_internal\docs\*.md" >nul 2>&1

echo @echo off > "%DIST_DIR%\run_server.bat"
echo title TTSG DICOM Gateway Server >> "%DIST_DIR%\run_server.bat"
echo cd /d "%%~dp0" >> "%DIST_DIR%\run_server.bat"
echo TTSG_DicomGateway.exe >> "%DIST_DIR%\run_server.bat"
echo pause >> "%DIST_DIR%\run_server.bat"

:: 4. Rao chan bao mat: ban phat hanh tuyet doi khong duoc chua private key ky license
findstr /s /m /c:"PRIVATE KEY-----" "%DIST_DIR%\*" >nul 2>&1
if not errorlevel 1 goto KEY_LEAK

echo.
echo ===============================================================================
echo   [THANH CONG] DA DONG GOI BAN PHAT HANH THUONG MAI THANH CONG!
echo ===============================================================================
echo   File chay chinh: %CD%\%DIST_DIR%\TTSG_DicomGateway.exe
echo ===============================================================================
echo.

if /i "%NOPAUSE%"=="nopause" exit /b 0
if exist "%DIST_DIR%\TTSG_DicomGateway.exe" explorer.exe /select,"%CD%\%DIST_DIR%\TTSG_DicomGateway.exe"
pause
exit /b 0

:KEY_LEAK
echo.
echo [LOI BAO MAT] Phat hien PRIVATE KEY trong %DIST_DIR% - HUY ban phat hanh!
echo Kiem tra lai excludes trong TTSG_DicomGateway.spec.
rmdir /s /q "%DIST_DIR%"
if /i not "%NOPAUSE%"=="nopause" pause
exit /b 1

:BUILD_ERROR
echo.
echo [LOI] Qua trinh dong goi gap su co. Kiem tra xem co file exe nao dang chay khong.
echo.
if /i not "%NOPAUSE%"=="nopause" pause
exit /b 1
