from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import uvicorn
from sqlalchemy import text

from .app import create_app
from .services.bootstrap import is_setup
from .settings import Settings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="local-agent-studio")
    subcommands = parser.add_subparsers(dest="command", required=True)
    serve = subcommands.add_parser("serve", help="Start the loopback server")
    serve.add_argument("--env", choices=["production", "development", "test"], default=None)
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    diagnose = subcommands.add_parser("diagnose", help="Print non-sensitive runtime diagnostics")
    diagnose.add_argument("--env", choices=["production", "development", "test"], default=None)
    backup = subcommands.add_parser("backup", help="Create a local SQLite backup")
    backup.add_argument("--env", choices=["production", "development", "test"], default=None)
    return parser


def main() -> None:
    args = _parser().parse_args()
    settings = Settings.from_env(getattr(args, "env", None))
    if args.command == "serve":
        if args.host:
            os.environ["LAS_HOST"] = args.host
        if args.port:
            os.environ["LAS_PORT"] = str(args.port)
        settings = Settings.from_env(args.env)
        app = create_app(settings)
        uvicorn.run(app, host=settings.host, port=settings.port, access_log=True, log_level="info")
        return
    app = create_app(settings)
    if args.command == "backup":
        from datetime import UTC, datetime

        destination = app.state.paths.backups / f"studio-{datetime.now(UTC):%Y%m%d-%H%M%S}.db"
        app.state.database.backup(destination)
        print(json.dumps({"status": "ok", "backup": str(destination)}, ensure_ascii=False))
        return
    with app.state.database.session() as session:
        session.execute(text("SELECT 1"))
    payload = {
        "environment": settings.environment,
        "host": settings.host,
        "port": settings.port,
        "data_dir": str(settings.data_dir),
        "data_dir_exists": Path(settings.data_dir).exists(),
        "database_exists": app.state.paths.database.exists(),
        "setup_completed": is_setup(app.state.database),
        "platform": os.name,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
