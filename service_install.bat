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

:: Dung va go service cu neu ton tai
echo [*] Dang kiem tra va dung service cu...
TTSG_Service.exe stop >nul 2>&1
TTSG_Service.exe uninstall >nul 2>&1
sc.exe stop TTSG_DicomGateway >nul 2>&1
sc.exe delete TTSG_DicomGateway >nul 2>&1
timeout /t 1 /nobreak >nul

echo [*] Dang dang ky Windows Service he thong voi WinSW...
TTSG_Service.exe install

if %errorLevel% equ 0 (
    echo [*] Mo Windows Firewall theo port trong config.yaml...
    TTSG_DicomGateway.exe --configure-firewall
    if errorlevel 1 echo [CANH BAO] Khong cau hinh duoc firewall - kiem tra lai bang tay.

    echo [*] Dang khoi dong Service chay ngam 24/7...
    TTSG_Service.exe start
    
    echo.
    echo ===============================================================================
    echo   [THANH CONG] DA CAI DAT VA KHOI DONG WINDOWS SERVICE THANH CONG!
    echo ===============================================================================
    echo   - Service Name: TTSG_DicomGateway (TTSG DICOM Gateway Service)
    echo   - Che do: Tu dong chay ngam 24/7 khi bat may (khong can dang nhap Windows)
    echo   - Tu dong phuc hoi (Auto-Restart) ngay lap tuc neu xay ra su co
    echo   - Truy cap Web Control Panel tai: http://localhost:^<web_ui.port trong config.yaml^>
    echo ===============================================================================
) else (
    echo.
    echo [LOI] Dang ky Service that bai. Vui long kiem tra quyen Admin.
)

echo.
pause

