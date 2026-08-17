[CmdletBinding()]
param()

. (Join-Path $PSScriptRoot "common.ps1")

if (-not (Test-Path $script:RuntimePython)) { throw "Runtime is missing. Run install.ps1 first." }
if (Read-StudioProcess) { throw "Stop Local Agent Studio before updating." }
Set-StudioEnvironment

Write-Host "[1/4] Backing up the current database"
& $script:RuntimePython -m local_agent_studio backup --env production
if ($LASTEXITCODE -ne 0) { throw "Backup failed; update was not started." }

Write-Host "[2/4] Checking the source working tree"
$changes = & git -C $script:ProjectRoot status --porcelain
if ($LASTEXITCODE -ne 0) { throw "The source directory is not a Git checkout." }
if ($changes) { throw "The source checkout has local changes. Commit or restore them before updating." }
& git -C $script:ProjectRoot pull --ff-only
if ($LASTEXITCODE -ne 0) { throw "Git update failed. The backup remains available." }

Write-Host "[3/4] Refreshing pinned dependencies and application"
& $script:RuntimePython -m pip install --disable-pip-version-check -r (Join-Path $script:ProjectRoot "requirements.lock")
if ($LASTEXITCODE -ne 0) { throw "Dependency update failed." }
& $script:RuntimePython -m pip install --disable-pip-version-check --no-deps --force-reinstall $script:ProjectRoot
if ($LASTEXITCODE -ne 0) { throw "Application update failed." }

Write-Host "[4/4] Applying migrations and running diagnostics"
& $script:RuntimePython -m local_agent_studio diagnose --env production
if ($LASTEXITCODE -ne 0) { throw "Post-update diagnostics failed." }
Write-Host "Update complete. Run start.ps1 when ready."
