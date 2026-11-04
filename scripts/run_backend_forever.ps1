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

function Test-BackendPort {
    $ProbeAddress = $HostAddress
    if ($ProbeAddress -eq "0.0.0.0") { $ProbeAddress = "127.0.0.1" }
    if ($ProbeAddress -eq "::") { $ProbeAddress = "::1" }
    $Client = New-Object System.Net.Sockets.TcpClient
    try {
        $Connection = $Client.ConnectAsync($ProbeAddress, $Port)
        if (-not $Connection.Wait(1500)) { return $false }
        return $Client.Connected
    } catch {
        return $false
    } finally {
        $Client.Dispose()
    }
}

# One supervisor per port, including launches from the scheduled task and desktop.
$SupervisorMutex = New-Object System.Threading.Mutex($false, "Local\MediaCrawlerBackend-$Port")
$OwnsMutex = $false
try {
    try { $OwnsMutex = $SupervisorMutex.WaitOne(0) }
    catch [System.Threading.AbandonedMutexException] { $OwnsMutex = $true }
    if (-not $OwnsMutex) {
        Write-Host "[MediaCrawler] A backend supervisor for port $Port is already running. Skipping duplicate launch."
        return
    }
    $WaitingForPort = $false
    while ($true) {
        if (Test-BackendPort) {
            if (-not $WaitingForPort) {
                Write-Host "[MediaCrawler] Port $Port is already in use. Keeping the existing service; waiting for the port to become available."
            }
            $WaitingForPort = $true
            Start-Sleep -Seconds $RestartDelaySeconds
            continue
        }
        $WaitingForPort = $false
        Write-Host "[MediaCrawler] Starting backend on http://${HostAddress}:${Port}"
        & $PythonExe -m uvicorn api.main:app --host $HostAddress --port $Port
        $ExitCode = $LASTEXITCODE
        Write-Warning "[MediaCrawler] Backend exited with code $ExitCode. Restarting in $RestartDelaySeconds seconds..."
        Start-Sleep -Seconds $RestartDelaySeconds
    }
} finally {
    if ($OwnsMutex) { $SupervisorMutex.ReleaseMutex() }
    $SupervisorMutex.Dispose()
}
