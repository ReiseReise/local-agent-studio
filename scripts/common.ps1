Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $env:LOCALAPPDATA) {
    throw "LOCALAPPDATA is unavailable. Run this script inside the target Windows user session."
}

$script:ProjectRoot = Split-Path -Parent $PSScriptRoot
$script:RuntimeRoot = Join-Path $env:LOCALAPPDATA "LocalAgentStudio"
$script:VenvRoot = Join-Path $script:RuntimeRoot "venv"
$script:RuntimePython = Join-Path $script:VenvRoot "Scripts\python.exe"
$script:PidFile = Join-Path $script:RuntimeRoot "service.json"

function Initialize-RuntimeFolders {
    @("data", "indexes", "logs", "backups", "secrets") | ForEach-Object {
        New-Item -ItemType Directory -Force -Path (Join-Path $script:RuntimeRoot $_) | Out-Null
    }
}

function Set-StudioEnvironment {
    $env:LAS_ENV = "production"
    $env:LAS_HOST = "127.0.0.1"
    $env:LAS_PORT = "8765"
    $env:LAS_DATA_DIR = $script:RuntimeRoot
}

function Get-BootstrapPython {
    $knownSystemPython = Join-Path $env:ProgramFiles "Python312\python.exe"
    if (Test-Path $knownSystemPython) {
        & $knownSystemPython -c "import sys; assert (3,12) <= sys.version_info[:2] < (3,14)"
        if ($LASTEXITCODE -eq 0) {
            return @{ Exe = $knownSystemPython; Prefix = @() }
        }
    }
    $knownUserPython = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
    if (Test-Path $knownUserPython) {
        & $knownUserPython -c "import sys; assert (3,12) <= sys.version_info[:2] < (3,14)"
        if ($LASTEXITCODE -eq 0) {
            return @{ Exe = $knownUserPython; Prefix = @() }
        }
    }
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        foreach ($version in @("-3.12", "-3.13")) {
            & $launcher.Source $version -c "import sys; assert (3,12) <= sys.version_info[:2] < (3,14)" 2>$null
            if ($LASTEXITCODE -eq 0) {
                return @{ Exe = $launcher.Source; Prefix = @($version) }
            }
        }
    }
    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($python) {
        & $python.Source -c "import sys; assert (3,12) <= sys.version_info[:2] < (3,14)"
        if ($LASTEXITCODE -eq 0) {
            return @{ Exe = $python.Source; Prefix = @() }
        }
    }
    throw "Python 3.12 or 3.13 was not found. Install 64-bit Python from python.org, then rerun install.ps1."
}

function Read-StudioProcess {
    if (-not (Test-Path $script:PidFile)) { return $null }
    try {
        $record = Get-Content $script:PidFile -Raw | ConvertFrom-Json
        foreach ($field in @("pid", "creation_time_utc", "process_executable", "command_line")) {
            if ($record.PSObject.Properties.Name -notcontains $field) { return $null }
        }
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($record.pid)" -ErrorAction Stop
        $creationTime = ([DateTime]$process.CreationDate).ToUniversalTime().ToString("o")
        if ($creationTime -ne $record.creation_time_utc) { return $null }
        if (-not [String]::Equals(
            [String]$process.ExecutablePath,
            [String]$record.process_executable,
            [StringComparison]::OrdinalIgnoreCase
        )) { return $null }
        if ($process.CommandLine -ne $record.command_line) { return $null }
        if ($process.CommandLine -notlike "*-m local_agent_studio serve --env production*") { return $null }
        return $process
    } catch {
        return $null
    }
}
