from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine
from sqlalchemy.orm import Session


class DatabasePolicy(Protocol):
    name: str

    def create_engine(self, data_dir: Path) -> Engine: ...

    def configure_connection(self, connection: Any) -> None: ...

    def begin_write(self, session: Session) -> None: ...


class SQLitePolicy:
    name = "sqlite"

    def create_engine(self, data_dir: Path) -> Engine:
        return create_engine(
            URL.create("sqlite", database=str(data_dir / "nila.db")),
            connect_args={"check_same_thread": False, "timeout": 5},
        )

    def configure_connection(self, connection: Any) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    def begin_write(self, session: Session) -> None:
        session.execute(text("BEGIN IMMEDIATE"))
