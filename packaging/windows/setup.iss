#define AppName "BAAS Capture Agent"
#define TaskName "BAAS Capture Agent"
#define IconTaskName "BAAS Capture Agent icon"
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
Source: "tasks.ps1"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Check the fingerprint reader"; Filename: "http://127.0.0.1:7501"
Name: "{group}\Fingerprint reader icon"; Filename: "{app}\baas-capture-agent.exe"
Name: "{group}\Reader check (probe)"; Filename: "{app}\baas-probe.exe"

[Run]
Filename: "{sys}\pnputil.exe"; Parameters: "/scan-devices"; Flags: runhidden; StatusMsg: "Asking Windows to find the fingerprint reader's driver..."
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\tasks.ps1"" -Exe ""{app}\baas-capture-agent.exe"""; Flags: runhidden; StatusMsg: "Starting the agent with Windows..."
Filename: "{app}\baas-capture-agent.exe"; Flags: nowait; StatusMsg: "Showing the reader icon..."
Filename: "http://127.0.0.1:7501"; Description: "Open the reader check page"; Flags: postinstall shellexec skipifsilent nowait

[UninstallRun]
Filename: "{sys}\schtasks.exe"; Parameters: "/End /TN ""{#IconTaskName}"""; Flags: runhidden; RunOnceId: "EndIconTask"
Filename: "{sys}\schtasks.exe"; Parameters: "/End /TN ""{#TaskName}"""; Flags: runhidden; RunOnceId: "EndTask"
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM baas-capture-agent.exe"; Flags: runhidden; RunOnceId: "KillAgent"
Filename: "{sys}\schtasks.exe"; Parameters: "/Delete /F /TN ""{#TaskName}"""; Flags: runhidden; RunOnceId: "DeleteTask"
Filename: "{sys}\schtasks.exe"; Parameters: "/Delete /F /TN ""{#IconTaskName}"""; Flags: runhidden; RunOnceId: "DeleteIconTask"

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
begin
  Exec(ExpandConstant('{sys}\schtasks.exe'), '/End /TN "{#IconTaskName}"', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Exec(ExpandConstant('{sys}\schtasks.exe'), '/End /TN "{#TaskName}"', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM baas-capture-agent.exe', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM baas-probe.exe', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Sleep(1000);
  Result := '';
end;
