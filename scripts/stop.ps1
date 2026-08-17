[CmdletBinding()]
param()

. (Join-Path $PSScriptRoot "common.ps1")

$process = Read-StudioProcess
if (-not $process) {
    if (Test-Path $script:PidFile) {
        Write-Warning "The PID record is stale or does not belong to Local Agent Studio; no process was stopped."
        Remove-Item -Force $script:PidFile
    } else {
        Write-Host "Local Agent Studio is not running."
    }
    exit 0
}

Stop-Process -Id $process.ProcessId
Wait-Process -Id $process.ProcessId -Timeout 10 -ErrorAction SilentlyContinue
if (Get-Process -Id $process.ProcessId -ErrorAction SilentlyContinue) {
    throw "The service did not stop cleanly. No force-kill was attempted."
}
Remove-Item -Force $script:PidFile -ErrorAction SilentlyContinue
Write-Host "Local Agent Studio stopped."
