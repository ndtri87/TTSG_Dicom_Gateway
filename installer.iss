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
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
; Copy tat ca file binary va giao dien (Loai bo toan bo file markdown .md)
Source: "dist\TTSG_DicomGateway\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "*.md,config.yaml"

; File config.yaml khong bi ghi de neu da ton tai
Source: "dist\TTSG_DicomGateway\config.yaml"; DestDir: "{app}"; Flags: onlyifdoesntexist

[Dirs]
Name: "{app}"; Permissions: users-full
Name: "{app}\data"; Permissions: users-full
Name: "{app}\logs"; Permissions: users-full

[Icons]
Name: "{group}\{#MyAppName} Web Control Panel"; Filename: "{#MyAppURL}"; IconFilename: "{app}\static\favicon.ico"
Name: "{group}\Khởi Động Lại Service (Restart Service)"; Filename: "{app}\TTSG_Service.exe"; Parameters: "restart"; IconFilename: "{app}\static\favicon.ico"
Name: "{group}\Chỉnh Sửa Cấu Hình (config.yaml)"; Filename: "notepad.exe"; Parameters: """{app}\config.yaml"""
Name: "{group}\Gỡ Cài Đặt {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName} Control Panel"; Filename: "{#MyAppURL}"; IconFilename: "{app}\static\favicon.ico"; Tasks: desktopicon

[Run]
; 1. Mo cong Windows Firewall cho Web UI (5000) va DICOM Storage Commitment (105)
Filename: "netsh.exe"; Parameters: "advfirewall firewall add rule name=""TTSG DICOM Gateway Web UI"" dir=in action=allow protocol=TCP localport=5000"; Flags: runhidden waituntilterminated; StatusMsg: "Dang thiet lap Windows Firewall..."
Filename: "netsh.exe"; Parameters: "advfirewall firewall add rule name=""TTSG DICOM Storage Commitment"" dir=in action=allow protocol=TCP localport=105"; Flags: runhidden waituntilterminated; StatusMsg: "Dang thiet lap Windows Firewall cho DICOM..."

; 2. Dang ky va khoi dong Windows Service chay ngam 24/7
Filename: "{app}\TTSG_Service.exe"; Parameters: "install"; Flags: runhidden waituntilterminated; StatusMsg: "Dang dang ky Windows Service chay ngam 24/7..."
Filename: "{app}\TTSG_Service.exe"; Parameters: "start"; Flags: runhidden waituntilterminated; StatusMsg: "Dang khoi dong DICOM Gateway Service..."

; 3. Mo trinh duyet Web vao trang quan tri
Filename: "{#MyAppURL}"; Description: "Mo Web Control Panel sau khi cai dat"; Flags: postinstall shellexec skipifsilent

[UninstallRun]
; Dung va go Service he thong truoc khi go cai dat
Filename: "{app}\TTSG_Service.exe"; Parameters: "stop"; Flags: runhidden waituntilterminated; RunOnceId: "TTSG_StopService"
Filename: "{app}\TTSG_Service.exe"; Parameters: "uninstall"; Flags: runhidden waituntilterminated; RunOnceId: "TTSG_UninstallService"
Filename: "netsh.exe"; Parameters: "advfirewall firewall delete rule name=""TTSG DICOM Gateway Web UI"""; Flags: runhidden waituntilterminated; RunOnceId: "TTSG_DelFw1"
Filename: "netsh.exe"; Parameters: "advfirewall firewall delete rule name=""TTSG DICOM Storage Commitment"""; Flags: runhidden waituntilterminated; RunOnceId: "TTSG_DelFw2"
