# Registers a nightly Windows Task Scheduler job that runs `manage.py backup_now`.
# Run this once, from an elevated PowerShell prompt, inside the project folder.
#
# Usage:
#   cd D:\Projects\Titans
#   .\scripts\schedule_backup.ps1

$ProjectDir = (Get-Location).Path
$Python = Join-Path $ProjectDir "venv\Scripts\python.exe"
$Manage = Join-Path $ProjectDir "manage.py"

$Action = New-ScheduledTaskAction -Execute $Python -Argument "`"$Manage`" backup_now" -WorkingDirectory $ProjectDir
$Trigger = New-ScheduledTaskTrigger -Daily -At 2:00AM
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd

Register-ScheduledTask -TaskName "TitansCRM-NightlyBackup" -Action $Action -Trigger $Trigger -Settings $Settings -Description "Nightly database + media backup for the Titans Windows CRM" -Force

Write-Host "Scheduled task 'TitansCRM-NightlyBackup' created: runs every day at 2:00 AM."
Write-Host "Remember to also copy the backups\ folder off this machine (cloud sync / external drive) -- see DEPLOYMENT.md."
