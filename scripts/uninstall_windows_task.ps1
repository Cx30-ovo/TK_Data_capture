param(
    [string]$TaskName = "MediaCrawlerBackend"
)

$ErrorActionPreference = "Stop"
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Host "Scheduled task removed: $TaskName"
