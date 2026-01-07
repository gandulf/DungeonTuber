; -- Example1.iss --
; Demonstrates copying 3 files and creating an icon.

; SEE THE DOCUMENTATION FOR DETAILS ON CREATING .ISS SCRIPT FILES!

[Setup]
AppName=Dungeon Tuber
AppVersion=0.1.0
WizardStyle=modern dynamic
WizardImageFile=docs/splash.png
DefaultDirName={autopf}\DungeonTuber
DefaultGroupName=DungeonTuber
UninstallDisplayIcon={app}\DungeonTuber.exe
Compression=lzma2
SolidCompression=yes
OutputDir=userdocs:DungeonTuber

[Files]
Source: "DungeonTuber.dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\DungeonTuber"; Filename: "{app}\DungeonTuber.exe"; WorkingDir: "{app}"
Name: "{commondesktop}\DungeonTuber"; Filename: "{app}\DungeonTuber.exe"; WorkingDir: "{app}"
Name: "{group}\Uninstall DungeonTuber"; Filename: "{uninstallexe}"


