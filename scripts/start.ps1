[CmdletBinding()]
param([switch]$NoBrowser)

. (Join-Path $PSScriptRoot "common.ps1")

if (-not (Test-Path $script:RuntimePython)) {
    throw "Local Agent Studio is not installed. Run scripts\install.ps1 first."
}
Initialize-RuntimeFolders
Set-StudioEnvironment

$existing = Read-StudioProcess
if ($existing) {
    Write-Host "Local Agent Studio is already running (PID $($existing.ProcessId))."
    if (-not $NoBrowser) { Start-Process "http://127.0.0.1:8765/admin" }
    exit 0
}
if (Test-Path $script:PidFile) { Remove-Item -Force $script:PidFile }

try {
    Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "http://127.0.0.1:8765/healthz" | Out-Null
    throw "Port 8765 is already serving an unrecognized process. Refusing to start."
} catch [System.Net.WebException] {
    # Expected when the fixed loopback port is free.
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$stdout = Join-Path $script:RuntimeRoot "logs\service-$stamp.out.log"
$stderr = Join-Path $script:RuntimeRoot "logs\service-$stamp.err.log"
$process = Start-Process -FilePath $script:RuntimePython `
    -ArgumentList @("-m", "local_agent_studio", "serve", "--env", "production") `
    -WorkingDirectory $script:ProjectRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr

try {
    $identity = Get-CimInstance Win32_Process -Filter "ProcessId = $($process.Id)" -ErrorAction Stop
    if ($identity.CommandLine -notlike "*-m local_agent_studio serve --env production*") {
        throw "Started process command line did not match the expected service."
    }
} catch {
    if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
    throw "Unable to establish the service process identity."
}

@{
    pid = $process.Id
    started_at = (Get-Date).ToUniversalTime().ToString("o")
    launch_executable = $script:RuntimePython
    process_executable = $identity.ExecutablePath
    command_line = $identity.CommandLine
    creation_time_utc = ([DateTime]$identity.CreationDate).ToUniversalTime().ToString("o")
} | ConvertTo-Json | Set-Content -Encoding UTF8 $script:PidFile

$healthy = $false
for ($attempt = 0; $attempt -lt 40; $attempt++) {
    Start-Sleep -Milliseconds 500
    if ($process.HasExited) { break }
    try {
        $response = Invoke-RestMethod -TimeoutSec 2 "http://127.0.0.1:8765/healthz"
        if ($response.status -eq "alive") { $healthy = $true; break }
    } catch { }
}
if (-not $healthy) {
    if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
    Remove-Item -Force $script:PidFile -ErrorAction SilentlyContinue
    throw "Service did not become healthy. Read $stderr"
}

Write-Host "Local Agent Studio is running at http://127.0.0.1:8765/admin"
if (-not $NoBrowser) { Start-Process "http://127.0.0.1:8765/admin" }
