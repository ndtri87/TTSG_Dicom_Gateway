@echo off
title Go Cai Dat Windows Service - TTSG DICOM Gateway
cd /d %~dp0

echo ===============================================================================
echo   GO BO WINDOWS SERVICE - TTSG DICOM GATEWAY
echo ===============================================================================
echo.

:: Kiem tra quyen Administrator
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [CANH BAO] Ban can chay file nay bang quyen Administrator (Run as administrator)!
    echo.
    pause
    exit /b 1
)

set "SERVICE_NAME=TTSG_DicomGateway"

echo [*] Dang dung Service %SERVICE_NAME%...
sc.exe stop %SERVICE_NAME% >nul 2>&1
timeout /t 2 /nobreak >nul

echo [*] Dang xoa Service khoi he thong Windows...
sc.exe delete %SERVICE_NAME%

if %errorLevel% equ 0 (
    echo [*] Xoa cac luat Windows Firewall da tao...
    netsh advfirewall firewall delete rule name="TTSG DICOM Gateway Web UI" >nul 2>&1
    netsh advfirewall firewall delete rule name="TTSG DICOM Storage Commitment" >nul 2>&1

    echo.
    echo ===============================================================================
    echo   [THANH CONG] DA GO BO HOAN TOAN DICH VU TTSG DICOM GATEWAY!
    echo ===============================================================================
    echo   - Service da duoc dung va go bo khoi he thong.
    echo   - Neu muon xoa sach du lieu, ban co the xoa toan bo thu muc nay.
    echo ===============================================================================
) else (
    echo.
    echo [THONG BAO] Service khong ton tai hoac da duoc go bo truoc do.
)

echo.
pause
