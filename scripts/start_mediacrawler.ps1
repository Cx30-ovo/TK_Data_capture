$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendScript = Join-Path $PSScriptRoot "run_backend_forever.ps1"
$WebUiDir = Join-Path $ProjectRoot "webui"

Start-Process powershell.exe `
    -WorkingDirectory $ProjectRoot `
    -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-NoExit", "-File", $BackendScript)

Start-Process powershell.exe `
    -WorkingDirectory $WebUiDir `
    -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-NoExit", "-Command", "npm.cmd run dev")

Write-Host "MediaCrawler backend and WebUI startup commands were launched."
