; Setup script for pyinstaller or nuitka generated exe

#ifexist "dist\DungeonTuber\DungeonTuber.exe"
  #define SourceFolder "dist\DungeonTuber"
#endif
#ifexist "dist\DungeonTuber.dist\DungeonTuber.exe"
  #define SourceFolder "dist\DungeonTuber.dist"
#endif

#define AppVersion GetVersionNumbersString(SourceFolder+"\DungeonTuber.exe")

[Setup]
AppName=Dungeon Tuber
AppVersion={#AppVersion}
WizardStyle=modern dynamic
WizardImageFile=docs/splash.png
DefaultDirName={autopf}\DungeonTuber
DefaultGroupName=DungeonTuber
UninstallDisplayIcon={app}\DungeonTuber.exe
Compression=lzma2
SolidCompression=yes
OutputDir=./
OutputBaseFilename=DungeonTuber-{#AppVersion}

[Files]
Source: "{#SourceFolder}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\DungeonTuber"; Filename: "{app}\DungeonTuber.exe"; WorkingDir: "{app}"
Name: "{commondesktop}\DungeonTuber"; Filename: "{app}\DungeonTuber.exe"; WorkingDir: "{app}"
Name: "{group}\Uninstall DungeonTuber"; Filename: "{uninstallexe}"


