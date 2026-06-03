#define RawAppVersion GetEnv("APP_VERSION")
#if RawAppVersion == ""
#define AppVersion "0.1.0"
#else
#define AppVersion RawAppVersion
#endif

[Setup]
AppId={{3E52D47F-D6CB-42B9-9D31-5E8261F9B295}
AppName=PC Optimizer
AppVersion={#AppVersion}
AppPublisher=PC Optimizer
DefaultDirName={localappdata}\Programs\PC Optimizer
DefaultGroupName=PC Optimizer
DisableProgramGroupPage=yes
OutputDir=dist\installer
OutputBaseFilename=PCOptimizer-Windows-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\PCOptimizer.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "dist\PCOptimizer.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\PC Optimizer"; Filename: "{app}\PCOptimizer.exe"
Name: "{autodesktop}\PC Optimizer"; Filename: "{app}\PCOptimizer.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PCOptimizer.exe"; Description: "Launch PC Optimizer"; Flags: nowait postinstall skipifsilent
