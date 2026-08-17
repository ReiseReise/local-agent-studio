from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.engine = create_engine(
            f"sqlite:///{path.as_posix()}",
            connect_args={"check_same_thread": False, "timeout": 10},
            pool_pre_ping=True,
        )
        event.listen(self.engine, "connect", self._configure_sqlite)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)

    @staticmethod
    def _configure_sqlite(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.close()

    def initialize(self) -> None:
        config = Config()
        config.set_main_option("script_location", str(Path(__file__).resolve().parent / "migrations"))
        config.set_main_option("sqlalchemy.url", f"sqlite:///{self.path.as_posix()}")
        command.upgrade(config, "head")
        self._ensure_fts(self.engine)

    def backup(self, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as source, sqlite3.connect(destination) as target:
            source.backup(target)

    @staticmethod
    def _ensure_fts(engine: Engine) -> None:
        with engine.begin() as connection:
            try:
                connection.execute(
                    text(
                        "CREATE VIRTUAL TABLE IF NOT EXISTS document_chunks_fts "
                        "USING fts5(chunk_id UNINDEXED, source_id UNINDEXED, text, tokenize='trigram')"
                    )
                )
            except Exception:
                connection.execute(
                    text(
                        "CREATE VIRTUAL TABLE IF NOT EXISTS document_chunks_fts "
                        "USING fts5(chunk_id UNINDEXED, source_id UNINDEXED, text, tokenize='unicode61')"
                    )
                )

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
