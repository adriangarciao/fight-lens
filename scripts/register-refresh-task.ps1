<#
.SYNOPSIS
  Register (or replace) the "FightLens Refresh" Windows scheduled task.

.DESCRIPTION
  Runs scripts/refresh.ps1 daily at the given time as the current user, only while logged on
  (no stored password). If the machine was off at that time, it runs at the next opportunity.
  Uses the built-in Windows PowerShell: a Store-installed pwsh can't be launched by Task Scheduler.
  Remove it with: Unregister-ScheduledTask -TaskName "FightLens Refresh"
#>
param([string]$At = "09:00")

$script = Join-Path $PSScriptRoot "refresh.ps1"
$powershell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$action = New-ScheduledTaskAction -Execute $powershell `
    -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$script`""
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName "FightLens Refresh" -Action $action -Trigger $trigger -Settings $settings `
    -Description "Fetch UFC data, score finished bouts and store predictions for scheduled ones (no retraining)." `
    -Force | Out-Null
Get-ScheduledTask -TaskName "FightLens Refresh" | Select-Object TaskName, State
