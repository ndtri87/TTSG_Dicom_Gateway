@echo off
setlocal enabledelayedexpansion
cd /d %~dp0

echo ===============================================================================
echo   CONG CU DONG GOI BAN VA PHIEN BAN (.PKG) - TTSG DICOM GATEWAY
echo ===============================================================================
echo.

set /p VERSION="Nhap so hieu phien ban cap nhat (vi du: 2.1.0): "
if "%VERSION%"=="" set VERSION=2.1.0

set /p NOTES="Nhap ghi chu noi dung cap nhat: "
if "%NOTES%"=="" set NOTES=Ban cap nhat toi uu hieu suat va nang cap tinh nang.

echo.
echo [*] Dang tao file patch: TTSG_Gateway_Patch_v%VERSION%.pkg...

.venv\Scripts\python.exe patch_builder.py --version "%VERSION%" --notes "%NOTES%" --dist "dist\TTSG_DicomGateway" --out "TTSG_Gateway_Patch_v%VERSION%.pkg"

echo.
pause
