#ifndef AppVersion
  #define AppVersion "0.4.0"
#endif
#ifndef BundleDir
  #error BundleDir must be the native frozen app directory
#endif
#ifndef OutputDir
  #define OutputDir "..\..\dist"
#endif
[Setup]
AppId={{218B0C68-2843-4D38-8DC6-19AF3DD20C74}
AppName=PyMOL AI-Assistant
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\PyMOL AI-Assistant
DefaultGroupName=PyMOL AI-Assistant
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=PyMOL-AI-Assistant-{#AppVersion}-Windows-x64-Setup
SetupIconFile=..\..\icons\PyMOL.ico
UninstallDisplayIcon={app}\icons\PyMOL.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
ChangesAssociations=yes
[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\PyMOL AI-Assistant"; Filename: "{app}\PyMOL AI-Assistant.exe"; IconFilename: "{app}\icons\PyMOL.ico"
Name: "{autodesktop}\PyMOL AI-Assistant"; Filename: "{app}\PyMOL AI-Assistant.exe"; IconFilename: "{app}\icons\PyMOL.ico"; Tasks: desktopicon
[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked
[Run]
Filename: "{app}\PyMOL AI-Assistant.exe"; Description: "Launch PyMOL AI-Assistant and choose preferred file types"; Flags: nowait postinstall skipifsilent

[Registry]
Root: HKCU; Subkey: "Software\PyMOL AI-Assistant"; Flags: dontcreatekey uninsdeletekey
Root: HKCU; Subkey: "Software\RegisteredApplications"; ValueName: "PyMOL AI-Assistant"; Flags: dontcreatekey uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\PyMOLAI.pdb"; Flags: dontcreatekey uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\.pdb\OpenWithProgids"; ValueName: "PyMOLAI.pdb"; Flags: dontcreatekey uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\PyMOLAI.cif"; Flags: dontcreatekey uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\.cif\OpenWithProgids"; ValueName: "PyMOLAI.cif"; Flags: dontcreatekey uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\PyMOLAI.mmcif"; Flags: dontcreatekey uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\.mmcif\OpenWithProgids"; ValueName: "PyMOLAI.mmcif"; Flags: dontcreatekey uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\PyMOLAI.pse"; Flags: dontcreatekey uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\.pse\OpenWithProgids"; ValueName: "PyMOLAI.pse"; Flags: dontcreatekey uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\PyMOLAI.mol"; Flags: dontcreatekey uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\.mol\OpenWithProgids"; ValueName: "PyMOLAI.mol"; Flags: dontcreatekey uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\PyMOLAI.sdf"; Flags: dontcreatekey uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\.sdf\OpenWithProgids"; ValueName: "PyMOLAI.sdf"; Flags: dontcreatekey uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\PyMOLAI.mol2"; Flags: dontcreatekey uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\.mol2\OpenWithProgids"; ValueName: "PyMOLAI.mol2"; Flags: dontcreatekey uninsdeletevalue
