from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    root: Path
    data: Path
    uploads: Path
    indexes: Path
    logs: Path
    backups: Path
    secrets: Path
    database: Path

    @classmethod
    def create(cls, root: Path) -> RuntimePaths:
        root = root.resolve()
        result = cls(
            root=root,
            data=root / "data",
            uploads=root / "data" / "uploads",
            indexes=root / "indexes",
            logs=root / "logs",
            backups=root / "backups",
            secrets=root / "secrets",
            database=root / "data" / "studio.db",
        )
        for directory in (
            result.root,
            result.data,
            result.uploads,
            result.indexes,
            result.logs,
            result.backups,
            result.secrets,
        ):
            directory.mkdir(parents=True, exist_ok=True)
            if os.name != "nt":
                directory.chmod(0o700)
        return result
