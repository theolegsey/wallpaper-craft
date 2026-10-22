; Скрипт установщика LiveWall (Inno Setup 6)
; Компиляция: ISCC livewall.iss  (после того как собрана папка dist\LiveWall)

#define MyAppName "LiveWall"
#define MyAppVersion "1.0.0"
#define MyAppExe "LiveWall.exe"

[Setup]
AppId={{8E2F6B1C-4A7D-4D3B-9C55-2B7E1F0A9D43}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppName}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExe}
OutputDir=installer_output
OutputBaseFilename=LiveWall-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Установка без прав администратора по умолчанию (в папку пользователя),
; но можно выбрать установку для всех пользователей в диалоге
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
CloseApplications=yes
DisableProgramGroupPage=yes

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "Запускать LiveWall вместе с Windows"; GroupDescription: "Дополнительно:"

[Files]
Source: "dist\LiveWall\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: """{app}\{#MyAppExe}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Запустить {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Закрываем программу перед удалением, чтобы файлы не были заняты
Filename: "taskkill"; Parameters: "/F /IM {#MyAppExe}"; Flags: runhidden; RunOnceId: "KillLiveWall"
