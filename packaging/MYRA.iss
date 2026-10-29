; Inno Setup script for MYRA.
; Personal data in {localappdata}\MYRA is deliberately not an install file,
; so updating or uninstalling the program does not delete owner data.

#define MyAppName "MYRA"
#define MyAppVersion "3.0-python-native"
#define MyAppExeName "MYRA.exe"

[Setup]
AppId={{B64AD161-0EEF-4B7C-9FA5-A37A80D5D641}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={localappdata}\Programs\MYRA
DefaultGroupName=MYRA
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist\installer
OutputBaseFilename=MYRA-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\assets\myra.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a Desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: checked

[Files]
Source: "..\dist\MYRA\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\MYRA"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\MYRA"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch MYRA"; Flags: nowait postinstall skipifsilent
