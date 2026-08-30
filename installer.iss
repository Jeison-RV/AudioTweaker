[Setup]
AppName=AudioTweaker
AppVersion=1.0.0
AppPublisher=Jeison Ramirez Vallejo
AppPublisherURL=https://github.com/Jeison-RV/AudioTweaker
DefaultDirName={autopf}\AudioTweaker
DefaultGroupName=AudioTweaker
OutputDir=dist
OutputBaseFilename=AudioTweaker-Setup
Compression=lzma
SolidCompression=yes
PrivilegesRequired=admin
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\AudioTweaker.exe

[Files]
Source: "dist\AudioTweaker.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\AudioTweaker"; Filename: "{app}\AudioTweaker.exe"
Name: "{commondesktop}\AudioTweaker"; Filename: "{app}\AudioTweaker.exe"

[Run]
Filename: "{app}\AudioTweaker.exe"; Description: "Abrir AudioTweaker"; Flags: nowait postinstall skipifsilent
