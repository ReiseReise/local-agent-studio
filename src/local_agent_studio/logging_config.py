from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(log_dir: Path, max_bytes: int) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger("local_agent_studio")
    root.setLevel(logging.INFO)
    if root.handlers:
        return
    handler = RotatingFileHandler(
        log_dir / "studio.log",
        maxBytes=max_bytes,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root.addHandler(handler)
