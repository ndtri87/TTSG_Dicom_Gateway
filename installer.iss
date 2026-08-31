; Inno Setup Script cho TTSG DICOM Gateway
; Tao file cai dat Setup.exe 1-Click chuan Y Te

#define MyAppName "TTSG DICOM Gateway"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "Tam Tri Saigon Hospital Solutions"
#define MyAppURL "http://localhost:5000"
#define MyAppExeName "TTSG_DicomGateway.exe"

[Setup]
AppId={{D37B4C82-95E2-4C10-86A9-51B4791E428F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=dist
OutputBaseFilename=TTSG_DicomGateway_Setup_v2.0
SetupIconFile=static\favicon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
; Copy tat ca file binary va giao dien
Source: "dist\TTSG_DicomGateway\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "config.yaml"

; File config.yaml khong bi ghi de neu da ton tai
Source: "dist\TTSG_DicomGateway\config.yaml"; DestDir: "{app}"; Flags: onlyifdoesntexist

[Icons]
Name: "{group}\{#MyAppName} Web Control Panel"; Filename: "{#MyAppURL}"; IconFilename: "{app}\static\favicon.ico"
Name: "{group}\Chinh Sua Cau Hinh (config.yaml)"; Filename: "notepad.exe"; Parameters: """{app}\config.yaml"""
Name: "{group}\Gỡ Cài Đặt {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName} Control Panel"; Filename: "{#MyAppURL}"; IconFilename: "{app}\static\favicon.ico"; Tasks: desktopicon

[Run]
; Tu dong dang ky va chay Windows Service ngam ngay sau khi cai dat xong
Filename: "{app}\service_install.bat"; Description: "Khoi dong Windows Service tu dong chay ngam 24/7"; StatusMsg: "Dang dang ky Windows Service va mo Firewall..."; Flags: runhidden waituntilterminated

; Mo trinh duyet Web vao trang quan tri
Filename: "{#MyAppURL}"; Description: "Mo Web Control Panel sau khi cai dat"; Flags: postinstall shellexec skipifsilent

[UninstallRun]
; Tu dong dung va go Windows Service truoc khi xoa file
Filename: "{app}\service_uninstall.bat"; Flags: runhidden waituntilterminated
