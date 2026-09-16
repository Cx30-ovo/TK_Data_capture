param(
    [string]$TaskName = "MediaCrawlerBackend"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendScript = Join-Path $PSScriptRoot "run_backend_forever.ps1"
$PowerShellExe = (Get-Command powershell.exe).Source

$Action = New-ScheduledTaskAction `
    -Execute $PowerShellExe `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$BackendScript`"" `
    -WorkingDirectory $ProjectRoot

$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Start MediaCrawler backend at user logon and restart it on failure." `
    -Force | Out-Null

Write-Host "Scheduled task installed: $TaskName"
