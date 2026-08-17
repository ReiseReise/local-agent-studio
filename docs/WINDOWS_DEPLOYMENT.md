# Windows deployment

## Prerequisites

- Windows 11 under the same user account that will run the service;
- 64-bit Python 3.12 or 3.13 with the Python launcher;
- Git only when installing from a clone or using `update.ps1`;
- no administrator privilege is required for the default loopback installation.

## Install and start

From a PowerShell window opened in the project directory:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

The installer creates an isolated environment under `%LOCALAPPDATA%\LocalAgentStudio\venv`, installs the pinned dependency set, applies database migrations, and verifies DPAPI-backed startup. It never installs or changes Siver, wxautox4, WeChat, firewall rules, or Windows login settings.

Open <http://127.0.0.1:8765/admin/setup>, create the first administrator password, add a model, test it, and publish a prompt. `/readyz` remains unavailable until setup, an active model, and a published prompt are all ready.

When Windows runs inside Parallels or another VM, disable automatic VM pausing before treating the service as always-on. A paused VM also pauses the loopback API; this is not an application crash and cannot be repaired by an in-guest watchdog.

## Operations

```powershell
.\scripts\diagnose.ps1
.\scripts\stop.ps1
.\scripts\update.ps1
.\scripts\uninstall.ps1
```

- `update.ps1` refuses a dirty checkout, creates a database backup, uses `git pull --ff-only`, applies migrations, and leaves the service stopped for an explicit restart.
- `uninstall.ps1` removes only the isolated Python runtime. It deliberately preserves all user data.
- Removing `%LOCALAPPDATA%\LocalAgentStudio` is a separate destructive action and is never automated by the repository.

## Recovery boundary

Database backups contain encrypted secrets that remain bound to the Windows user through DPAPI. A copied backup can restore ordinary configuration and text, but encrypted keys are not portable to another Windows account. Use the sanitized JSON export for migration and re-enter keys on the destination machine.
