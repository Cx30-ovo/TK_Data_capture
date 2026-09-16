param(
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8080,
    [int]$RestartDelaySeconds = 10
)

$ErrorActionPreference = "Continue"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

Set-Location $ProjectRoot

if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Python virtual environment not found: $PythonExe"
}

while ($true) {
    Write-Host "[MediaCrawler] Starting backend on http://${HostAddress}:${Port}"
    & $PythonExe -m uvicorn api.main:app --host $HostAddress --port $Port
    $ExitCode = $LASTEXITCODE
    Write-Warning "[MediaCrawler] Backend exited with code $ExitCode. Restarting in $RestartDelaySeconds seconds..."
    Start-Sleep -Seconds $RestartDelaySeconds
}
