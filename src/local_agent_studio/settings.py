from __future__ import annotations

import os
import platform
from dataclasses import dataclass, replace
from pathlib import Path

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _default_data_dir() -> Path:
    if platform.system() == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            raise RuntimeError("LOCALAPPDATA is required on Windows")
        return Path(local_app_data) / "LocalAgentStudio"
    return Path.home() / ".local" / "share" / "LocalAgentStudio"


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str = "production"
    host: str = "127.0.0.1"
    port: int = 8765
    data_dir: Path = Path(".")
    max_upload_bytes: int = 20 * 1024 * 1024
    reply_max_chars: int = 300
    log_retention_days: int = 14
    log_max_bytes: int = 50 * 1024 * 1024
    cookie_name: str = "las_admin"
    secure_cookie: bool = False

    @classmethod
    def from_env(cls, environment: str | None = None) -> Settings:
        env = environment or os.environ.get("LAS_ENV", "production").strip().lower()
        data_dir = Path(os.environ.get("LAS_DATA_DIR", str(_default_data_dir()))).expanduser().resolve()
        settings = cls(
            environment=env,
            host=os.environ.get("LAS_HOST", "127.0.0.1").strip(),
            port=int(os.environ.get("LAS_PORT", "8765")),
            data_dir=data_dir,
        )
        settings.validate()
        return settings

    def with_data_dir(self, data_dir: Path) -> Settings:
        return replace(self, data_dir=data_dir.resolve())

    def validate(self) -> None:
        if self.environment not in {"production", "development", "test"}:
            raise RuntimeError("LAS_ENV must be production, development, or test")
        if self.host not in LOOPBACK_HOSTS:
            raise RuntimeError("Local Agent Studio only binds to a loopback host")
        if not (1 <= self.port <= 65535):
            raise RuntimeError("LAS_PORT is invalid")
        if self.environment == "production" and platform.system() != "Windows":
            raise RuntimeError("Production mode is supported only on Windows")
