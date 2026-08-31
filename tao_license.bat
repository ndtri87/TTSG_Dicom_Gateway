@echo off
title Cong Cu Phat Hanh License Ban Quyen - TTSG DICOM Gateway
cd /d "%~dp0"

echo ===============================================================================
echo   CONG CU PHAT HANH LICENSE BAN QUYEN THUONG MAI - TTSG DICOM GATEWAY
echo ===============================================================================
echo.

set /p CUSTOMER="1. Nhap Ten Benh Vien / Khach Hang (Mac dinh: BV Tam Tri Sai Gon): "
if "%CUSTOMER%"=="" set "CUSTOMER=BV Tam Tri Sai Gon"

set /p HWID="2. Nhap Hardware ID cua may khach (Nhan Enter de ap dung cho MOI MAY [*]): "
if "%HWID%"=="" set "HWID=*"

set /p EXP="3. Nhap Han Dung YYYY-MM-DD (Nhan Enter de chon VINH VIEN [PERMANENT]): "
if "%EXP%"=="" set "EXP=PERMANENT"

set /p STATIONS="4. Nhap so luong phong kham toi da (Mac dinh: 100): "
if "%STATIONS%"=="" set "STATIONS=100"

echo.
echo [*] Dang tao chu ky so RSA 2048-bit va tao file license.key...
call .venv\Scripts\python.exe license_generator.py --customer "%CUSTOMER%" --hwid "%HWID%" --exp "%EXP%" --modalities "*" --stations %STATIONS% --plan "Ban Quyen Doanh Nghiep (Enterprise Edition)" --out "data/license.key"

if errorlevel 0 (
    if exist "dist\TTSG_DicomGateway\data\" copy /y "data\license.key" "dist\TTSG_DicomGateway\data\license.key" >nul
    if exist "C:\Program Files\TTSG DICOM Gateway\data\" copy /y "data\license.key" "C:\Program Files\TTSG DICOM Gateway\data\license.key" >nul
    
    echo.
    echo ===============================================================================
    echo [HUONG DAN SU DUNG FILE LICENSE.KEY]:
    echo 1. Ban co the copy file 'data\license.key' gui cho khach hang.
    echo 2. Khach hang co the vao Web Admin -^> Tab 'Ban Quyen va He Thong' -^> Nhan 'Kich Hoat / Upload License'.
    echo 3. Hoac copy truc tiep file vao thu muc: 'C:\Program Files\TTSG DICOM Gateway\data\license.key'.
    echo ===============================================================================
)

echo.
pause
