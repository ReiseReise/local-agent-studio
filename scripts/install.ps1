[CmdletBinding()]
param()

. (Join-Path $PSScriptRoot "common.ps1")

Initialize-RuntimeFolders
$bootstrap = Get-BootstrapPython

Write-Host "[1/4] Creating isolated runtime in $script:VenvRoot"
if (-not (Test-Path $script:RuntimePython)) {
    & $bootstrap.Exe @($bootstrap.Prefix) -m venv $script:VenvRoot
    if ($LASTEXITCODE -ne 0) { throw "Virtual environment creation failed." }
}

Write-Host "[2/4] Installing pinned dependencies"
& $script:RuntimePython -m pip install --disable-pip-version-check -r (Join-Path $script:ProjectRoot "requirements.lock")
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }

Write-Host "[3/4] Installing Local Agent Studio"
& $script:RuntimePython -m pip install --disable-pip-version-check --no-deps --force-reinstall $script:ProjectRoot
if ($LASTEXITCODE -ne 0) { throw "Application installation failed." }

Write-Host "[4/4] Initializing the DPAPI-protected local database"
Set-StudioEnvironment
& $script:RuntimePython -m local_agent_studio diagnose --env production
if ($LASTEXITCODE -ne 0) { throw "Runtime initialization failed." }

@{
    project_root = $script:ProjectRoot
    installed_at = (Get-Date).ToUniversalTime().ToString("o")
    version = "0.1.0"
} | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $script:RuntimeRoot "install.json")

Write-Host "Installation complete. Run scripts\start.ps1, then finish setup in the browser."
