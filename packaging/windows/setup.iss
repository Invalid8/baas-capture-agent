#define AppName "BAAS Capture Agent"
#define TaskName "BAAS Capture Agent"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6C3F4E1A-8B2D-4F7A-9E51-BAA5C0A9E7D2}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=BAAS project
AppPublisherURL=https://github.com/Invalid8/baas-capture-agent
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
OutputDir=..\..\dist
OutputBaseFilename=baas-capture-agent-setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\baas-capture-agent.exe

[Files]
Source: "..\..\dist\baas-capture-agent.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\dist\baas-probe.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Check the fingerprint reader"; Filename: "http://127.0.0.1:7501"
Name: "{group}\Start the capture agent"; Filename: "{app}\baas-capture-agent.exe"
Name: "{group}\Reader check (probe)"; Filename: "{app}\baas-probe.exe"

[Run]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM baas-capture-agent.exe"; Flags: runhidden; StatusMsg: "Stopping an older agent..."
Filename: "{sys}\pnputil.exe"; Parameters: "/scan-devices"; Flags: runhidden; StatusMsg: "Asking Windows to find the fingerprint reader's driver..."
Filename: "{sys}\schtasks.exe"; Parameters: "/Create /F /TN ""{#TaskName}"" /TR ""\""{app}\baas-capture-agent.exe\"""" /SC ONLOGON /RL HIGHEST"; Flags: runhidden; StatusMsg: "Starting the agent at every sign-in..."
Filename: "{sys}\schtasks.exe"; Parameters: "/Run /TN ""{#TaskName}"""; Flags: runhidden; StatusMsg: "Starting the agent..."
Filename: "http://127.0.0.1:7501"; Description: "Open the reader check page"; Flags: postinstall shellexec skipifsilent nowait

[UninstallRun]
Filename: "{sys}\schtasks.exe"; Parameters: "/End /TN ""{#TaskName}"""; Flags: runhidden; RunOnceId: "EndTask"
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM baas-capture-agent.exe"; Flags: runhidden; RunOnceId: "KillAgent"
Filename: "{sys}\schtasks.exe"; Parameters: "/Delete /F /TN ""{#TaskName}"""; Flags: runhidden; RunOnceId: "DeleteTask"
