@echo off
setlocal enabledelayedexpansion
cd /d %~dp0

echo ===============================================================================
echo   CONG CU DONG GOI THUONG MAI - TTSG DICOM GATEWAY SERVER (RELEASE BUILD)
echo ===============================================================================
echo.

:: 1. Kiem tra PyInstaller trong virtualenv
if not exist ".venv\Scripts\pyinstaller.exe" (
    echo [*] Dang cai dat PyInstaller vao moi truong .venv...
    .venv\Scripts\pip.exe install pyinstaller
    if errorlevel 1 (
        echo [LOI] Khong the cai dat PyInstaller. Vui long kiem tra ket noi mang.
        pause
        exit /b 1
    )
)

echo [*] Bat dau tien trinh bien dich & dong goi sang ma may nhi phan (Standalone Binary)...
echo [*] Vui long cho trong giay lat...
echo.

:: 2. Chay PyInstaller de dong goi Server
.venv\Scripts\pyinstaller.exe ^
    --onedir ^
    --name "TTSG_DicomGateway" ^
    --icon "static/favicon.ico" ^
    --add-data "templates;templates" ^
    --add-data "static;static" ^
    --hidden-import "waitress" ^
    --hidden-import "cryptography" ^
    --hidden-import "pydicom" ^
    --hidden-import "pynetdicom" ^
    --hidden-import "watchdog" ^
    --hidden-import "pypdfium2" ^
    --hidden-import "PIL" ^
    --hidden-import "yaml" ^
    --hidden-import "sqlite3" ^
    --hidden-import "werkzeug" ^
    --hidden-import "jinja2" ^
    --hidden-import "license_manager" ^
    --hidden-import "utils" ^
    --hidden-import "dicom_builder" ^
    --hidden-import "dicom_sender" ^
    --hidden-import "retry_worker" ^
    --hidden-import "worklist_client" ^
    --hidden-import "storage_commitment_listener" ^
    --noconfirm ^
    --clean ^
    main.py

if errorlevel 1 (
    echo.
    echo [LOI] Qua trinh dong goi gap su co. Xem chi tiet loi o tren.
    pause
    exit /b 1
)

:: 3. Chuan bi thu muc phan phoi Release
set "DIST_DIR=dist\TTSG_DicomGateway"

echo.
echo [*] Dang sao chep cac file cau hinh va cong cu bo tro vao ban phat hanh...

:: Copy config.yaml
if exist "config.yaml" (
    copy /y "config.yaml" "%DIST_DIR%\config.yaml" >nul
)

:: Copy Service Scripts
if exist "service_install.bat" (
    copy /y "service_install.bat" "%DIST_DIR%\service_install.bat" >nul
)
if exist "service_uninstall.bat" (
    copy /y "service_uninstall.bat" "%DIST_DIR%\service_uninstall.bat" >nul
)
if exist "docs\HUONG_DAN_TRIEN_KHAI_DICOM_GATEWAY.md" (
    copy /y "docs\HUONG_DAN_TRIEN_KHAI_DICOM_GATEWAY.md" "%DIST_DIR%\HUONG_DAN_TRIEN_KHAI.md" >nul
) else if exist "HUONG_DAN_TRIEN_KHAI_DICOM_GATEWAY.md" (
    copy /y "HUONG_DAN_TRIEN_KHAI_DICOM_GATEWAY.md" "%DIST_DIR%\HUONG_DAN_TRIEN_KHAI.md" >nul
)

:: Tao script run_server.bat chay truc tiep
(
    echo @echo off
    echo title TTSG DICOM Gateway Server
    echo cd /d %%~dp0
    echo echo ===============================================================================
    echo echo   TTSG DICOM GATEWAY SERVICE - MEDICAL PACS/RIS INTEGRATION ENGINE
    echo echo ===============================================================================
    echo echo.
    echo TTSG_DicomGateway.exe
    echo pause
) > "%DIST_DIR%\run_server.bat"

:: Tao Huong Dan Cai Dat
(
    echo ===============================================================================
    echo   HUONG DAN CAI DAT VA VAN HANH - TTSG DICOM GATEWAY SERVICE
    echo ===============================================================================
    echo.
    echo 1. CAU HINH THONG SO KET NOI:
    echo    - Mo file 'config.yaml' bang Notepad hoac Text Editor.
    echo    - Chinh sua thong so IP/Port PACS va RIS cua Benh vien/Phong kham.
    echo.
    echo 2. CHAY THU NGHIEM TRUC TIEP:
    echo    - Nhay dup chuot vao file 'run_server.bat'.
    echo    - Mo trinh duyet Web truy cap: http://localhost:5000
    echo.
    echo 3. DANG KY CHAY NGAM (WINDOWS SERVICE TU DONG KHOI DONG 24/7):
    echo    - Nhay chuot phai vao file 'service_install.bat' -^> Chon 'Run as administrator'.
    echo    - He thong se tu dong dang ky Windows Service va mo Firewall port 5000/105.
    echo.
    echo 4. GO CAI DAT SERVICE:
    echo    - Nhay chuot phai vao file 'service_uninstall.bat' -^> Chon 'Run as administrator'.
    echo.
    echo 5. KICH HOAT BAN QUYEN:
    echo    - Dang nhap Web Admin (User: trind / Mat khau: admin123)
    echo    - Vao tab 'Ban Quyen va He Thong', copy ma Hardware ID va gui cho nha san xuat
    echo      de nhan file 'license.key'.
    echo.
    echo ===============================================================================
) > "%DIST_DIR%\Huong_Dan_Cai_Dat.txt"

echo.
echo ===============================================================================
echo   [THANH CONG] DA DONG GOI BAN PHAT HANH THUONG MAI THANH CONG!
echo ===============================================================================
echo.
echo  Thu muc ban giao cho khach hang:
echo  ==^> %CD%\%DIST_DIR%
echo.
echo  Ban chi can nén hoac copy toan bo thu muc tren giao cho khach hang.
echo  Tuyet doi KHONG co bat ky file ma nguon .py nao bi lo!
echo ===============================================================================
echo.
pause
