# Run by the setup (as administrator). schtasks.exe can't change a task's power settings, and its defaults
# refuse to start on battery and stop a task after 3 days, so the tasks are registered here.
param([Parameter(Mandatory)][string]$Exe)

$ErrorActionPreference = "Stop"

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName "BAAS Capture Agent" -Force -Settings $settings `
    -Action (New-ScheduledTaskAction -Execute $Exe -Argument "--service") `
    -Trigger (New-ScheduledTaskTrigger -AtStartup) `
    -Principal (New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest) | Out-Null

Register-ScheduledTask -TaskName "BAAS Capture Agent icon" -Force -Settings $settings `
    -Action (New-ScheduledTaskAction -Execute $Exe) `
    -Trigger (New-ScheduledTaskTrigger -AtLogOn) `
    -Principal (New-ScheduledTaskPrincipal -GroupId "S-1-5-32-545" -RunLevel Highest) | Out-Null

Start-ScheduledTask -TaskName "BAAS Capture Agent"

for ($i = 0; $i -lt 40; $i++) {
    try {
        Invoke-RestMethod -Uri "http://127.0.0.1:7501/status" -TimeoutSec 2 | Out-Null
        exit 0
    } catch {
        Start-Sleep -Milliseconds 500
    }
}
Write-Error "The capture agent did not answer on http://127.0.0.1:7501 within 20 seconds."
exit 1
