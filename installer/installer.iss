; Installer Windows di Rugby Highlights (Inno Setup 6)
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{943097E5-4439-45F7-A290-6063EE1762AE}
AppName=Rugby Highlights
AppVersion={#AppVersion}
DefaultDirName={autopf}\Rugby Highlights
DefaultGroupName=Rugby Highlights
OutputDir=..\installer_out
OutputBaseFilename=RugbyHighlights-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName=Rugby Highlights

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"

[Tasks]
Name: "desktopicon"; Description: "Crea un'icona sul desktop"; GroupDescription: "Icone:"

[Files]
Source: "..\dist\RugbyHighlights\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion createallsubdirs

[Icons]
Name: "{group}\Rugby Highlights"; Filename: "{app}\RugbyHighlights.exe"
Name: "{autodesktop}\Rugby Highlights"; Filename: "{app}\RugbyHighlights.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\RugbyHighlights.exe"; Description: "Avvia Rugby Highlights"; Flags: nowait postinstall skipifsilent
