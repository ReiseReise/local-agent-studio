[CmdletBinding()]
param()

. (Join-Path $PSScriptRoot "common.ps1")

if (-not (Test-Path $script:RuntimePython)) {
    throw "Runtime is missing. Run scripts\install.ps1."
}
Set-StudioEnvironment
& $script:RuntimePython -m local_agent_studio diagnose --env production
if ($LASTEXITCODE -ne 0) { throw "Application diagnostics failed." }

$process = Read-StudioProcess
if ($process) {
    try {
        $health = Invoke-RestMethod -TimeoutSec 3 "http://127.0.0.1:8765/healthz"
        Write-Host "Process: running (PID $($process.ProcessId)); health: $($health.status)"
    } catch {
        Write-Warning "The recorded process exists but /healthz is unreachable."
    }
} else {
    Write-Host "Process: stopped"
}
