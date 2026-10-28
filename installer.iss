#ifndef BundleDir
  #error BundleDir is required
#endif
#ifndef Deliverables
  #error Deliverables is required
#endif
[Setup]
AppId={{33963C7F-9C78-486B-A19A-E12294A14402}
AppName=Orbit Display
AppVersion=0.4.0
AppPublisher=Orbit Display
DefaultDirName={localappdata}\Programs\Orbit Display
DisableDirPage=no
DefaultGroupName=Orbit Display
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#Deliverables}
OutputBaseFilename=Orbit-Display-0.4.0-Setup
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
SetupIconFile=assets\orbit.ico
WizardSizePercent=110
UninstallDisplayIcon={app}\OrbitDisplay.exe
CloseApplications=no
RestartApplications=no
SetupLogging=yes

[Languages]
Name: "ukrainian"; MessagesFile: "compiler:Languages\Ukrainian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Створити ярлик на робочому столі"; Flags: unchecked

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\Orbit Display"; Filename: "{app}\OrbitDisplay.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\Orbit Display"; Filename: "{app}\OrbitDisplay.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\OrbitDisplay.exe"; Description: "Відкрити Orbit Display"; Flags: nowait postinstall skipifsilent unchecked
