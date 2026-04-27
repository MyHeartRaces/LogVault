#define AppName "LogVault"
#ifndef AppVersion
#define AppVersion "0.0.0"
#endif

[Setup]
AppId={{8C16B880-7CB3-4B10-85F5-2E951E108F4C}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=LogVault
AppPublisherURL=https://github.com/MyHeartRaces/LogVault
AppSupportURL=https://github.com/MyHeartRaces/LogVault/issues
AppUpdatesURL=https://github.com/MyHeartRaces/LogVault/releases/latest
DefaultDirName={localappdata}\Programs\LogVault
DefaultGroupName=LogVault
DisableProgramGroupPage=yes
OutputDir=..\..\installer
OutputBaseFilename=LogVault-Setup-{#AppVersion}-x64
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
WizardStyle=modern
UninstallDisplayName=LogVault

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\..\dist\LogVault.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\LogVault"; Filename: "{app}\LogVault.exe"; WorkingDir: "{userdocs}"
Name: "{autodesktop}\LogVault"; Filename: "{app}\LogVault.exe"; WorkingDir: "{userdocs}"; Tasks: desktopicon

[Run]
Filename: "{app}\LogVault.exe"; Description: "Launch LogVault"; Flags: nowait postinstall skipifsilent
