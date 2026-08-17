[CmdletBinding()]
param()

. (Join-Path $PSScriptRoot "common.ps1")

if (Read-StudioProcess) { throw "Stop Local Agent Studio before uninstalling." }

if (Test-Path $script:VenvRoot) {
    $resolvedRuntime = (Resolve-Path $script:RuntimeRoot).Path.TrimEnd('\')
    $resolvedVenv = (Resolve-Path $script:VenvRoot).Path
    if (-not $resolvedVenv.StartsWith($resolvedRuntime + '\')) {
        throw "Runtime path validation failed; nothing was removed."
    }
    Remove-Item -Recurse -Force $resolvedVenv
}
Remove-Item -Force (Join-Path $script:RuntimeRoot "install.json") -ErrorAction SilentlyContinue

Write-Host "Application runtime removed. User data was preserved at $script:RuntimeRoot"
