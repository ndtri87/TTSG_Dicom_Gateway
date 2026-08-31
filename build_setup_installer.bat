@echo off
setlocal enabledelayedexpansion
cd /d %~dp0

echo ===============================================================================
echo   CONG CU DONG GOI BO CAI DAT CHUYEN NGHIEP (SETUP.EXE) - INNO SETUP
echo ===============================================================================
echo.

:: 1. Bien dich Server Binary neu chua co
if not exist "dist\TTSG_DicomGateway\TTSG_DicomGateway.exe" (
    echo [*] Chua thay ban build nhi phan, dang chay dong goi truoc...
    call build_server_exe.bat
)

:: 2. Tim trinh bien dich Inno Setup
set "ISCC_PATH="
if exist "C:\Users\%USERNAME%\AppData\Local\Programs\Inno Setup 6\ISCC.exe" (
    set "ISCC_PATH=C:\Users\%USERNAME%\AppData\Local\Programs\Inno Setup 6\ISCC.exe"
) else if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
) else if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    set "ISCC_PATH=C:\Program Files\Inno Setup 6\ISCC.exe"
)

if "%ISCC_PATH%"=="" (
    echo [LOI] Khong tim thay Inno Setup Compiler (ISCC.exe).
    echo Vui long cai dat Inno Setup 6.
    pause
    exit /b 1
)

echo [*] Dang bien dich bo cai dat 1 file duy nhat: TTSG_DicomGateway_Setup_v2.0.exe...
"%ISCC_PATH%" installer.iss

if errorlevel 1 (
    echo.
    echo [LOI] Bien dich Setup.exe that bai. Xem chi tiet ben tren.
    pause
    exit /b 1
)

echo.
echo ===============================================================================
echo   [THANH CONG] DA TAO FILE CAI DAT SETUP.EXE CHUYEN NGHIEP!
echo ===============================================================================
echo.
echo  File cai dat duy nhat ban giao cho khach hang:
echo  ==^> %CD%\dist\TTSG_DicomGateway_Setup_v2.0.exe
echo.
echo  Khach hang chi can nhay dup chuot vao file nay:
echo  Next -^> Next -^> Finish la he thong tu dong cai dat va chay ngam!
echo ===============================================================================
echo.
pause
