@echo off
title Cai Dat Windows Service - TTSG DICOM Gateway
cd /d %~dp0

echo ===============================================================================
echo   DANG KY CHAY NGAM (WINDOWS SERVICE) - TTSG DICOM GATEWAY
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
set "BIN_PATH=%~dp0TTSG_DicomGateway.exe"

echo [*] Dang dung service cu (neu co)...
sc.exe stop %SERVICE_NAME% >nul 2>&1
timeout /t 1 /nobreak >nul

echo [*] Dang dang ky Service he thong moi...
sc.exe create %SERVICE_NAME% binPath= "\"%BIN_PATH%\"" start= auto DisplayName= "TTSG DICOM Gateway Service"

if %errorLevel% equ 0 (
    echo [*] Cau hinh tu dong khoi dong lai khi gap su co (Auto-Recovery)...
    sc.exe failure %SERVICE_NAME% reset= 86400 actions= restart/5000/restart/5000/restart/10000
    
    echo [*] Mo cong Windows Firewall cho Web UI (Port 5000) va DICOM...
    netsh advfirewall firewall add rule name="TTSG DICOM Gateway Web UI" dir=in action=allow protocol=TCP localport=5000 >nul 2>&1
    netsh advfirewall firewall add rule name="TTSG DICOM Storage Commitment" dir=in action=allow protocol=TCP localport=105 >nul 2>&1

    echo [*] Dang khoi dong Service...
    sc.exe start %SERVICE_NAME%
    
    echo.
    echo ===============================================================================
    echo   [THANH CONG] DA CAI DAT VA KHOI DONG WINDOWS SERVICE THANH CONG!
    echo ===============================================================================
    echo   - Service Name: %SERVICE_NAME%
    echo   - Che do: Tu dong chay ngam 24/7 khi bat may (khong can dang nhap Windows)
    echo   - Truy cap Web Control Panel tai: http://localhost:5000
    echo ===============================================================================
) else (
    echo.
    echo [LOI] Dang ky Service that bai. Vui long kiem tra quyen Admin hoac file exe.
)

echo.
pause
