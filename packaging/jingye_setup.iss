; 净页 JingYe — Inno Setup 安装脚本
; 前提：已用 scripts/build_gui_onedir.ps1 生成 dist\JingYe\
; 编译：安装 Inno Setup 6 后执行 scripts/build_installer.ps1
; 或：ISCC.exe packaging\jingye_setup.iss
;
; 说明：
; - 本脚本把 onedir 绿色目录打成标准 Windows 安装包
; - 不改变程序逻辑，仅负责复制文件、快捷方式、卸载项

#define MyAppName "净页 JingYe"
#define MyAppNameEn "JingYe"
; 发版时与 pdf_dewatermark.__version__ / branding.APP_VERSION 保持一致
#define MyAppVersion "0.2.6"
#define MyAppPublisher "JingYe"
#define MyAppExeName "JingYe.exe"
#define MyAppURL "https://github.com"

; 相对本 .iss 所在 packaging/ 目录
#define DistDir "..\dist\JingYe"
#define OutputDir "..\dist\releases"
#define SetupIcon "app.ico"

[Setup]
AppId={{A8C3E1F2-9B4D-4E7A-8F21-1A2B3C4D5E6F}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppNameEn}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; 普通用户可装到自己目录时可用 lowest；装到 Program Files 需 admin
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
OutputDir={#OutputDir}
OutputBaseFilename=JingYe-Setup-{#MyAppVersion}
SetupIconFile={#SetupIcon}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
VersionInfoVersion={#MyAppVersion}.0
VersionInfoProductName={#MyAppName}
VersionInfoCompany={#MyAppPublisher}
; 安装后保留 data/output，卸载时不删用户数据见 [UninstallDelete] 策略
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
; 若本机 Inno 无中文语言包，可改为：
; Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标:"; Flags: unchecked

[Files]
; 整包 onedir（含 _internal、使用说明、VERSION 等）
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\使用说明"; Filename: "{app}\使用说明.txt"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 仅清理空目录；保留用户 output/data 内容（若存在文件则目录可能残留，属预期）
Type: dirifempty; Name: "{app}\logs"
Type: dirifempty; Name: "{app}\output"
Type: dirifempty; Name: "{app}\data"
