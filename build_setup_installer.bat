@echo off
title Dong Goi Bo Cai Dat Setup.exe - TTSG DICOM Gateway
cd /d "%~dp0"

echo ===============================================================================
echo   DONG GOI BO CAI DAT CHUYEN NGHIEP (SETUP.EXE) - TTSG DICOM GATEWAY
echo ===============================================================================
echo.

set ISCC_PATH=
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC_PATH=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
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
echo [BUOC 1/2] BIEN DICH MA NGUON SANG MA MAY (build_server_exe.bat)
echo ===============================================================================
call build_server_exe.bat nopause
if errorlevel 1 goto BUILD_ERROR

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
echo   File cai dat Setup 1-Click: %CD%\dist\TTSG_DicomGateway_Setup_v2.0.exe
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
