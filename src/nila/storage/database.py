from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import event
from sqlalchemy.orm import Session, sessionmaker

from nila.storage.dialects import DatabasePolicy, SQLitePolicy
from nila.storage.models import AuditEvent


class Database:
    def __init__(self, data_dir: Path, *, policy: DatabasePolicy | None = None) -> None:
        data_dir.mkdir(parents=True, exist_ok=True)
        self.policy: DatabasePolicy = policy if policy is not None else SQLitePolicy()
        self.engine = self.policy.create_engine(data_dir)
        event.listen(self.engine, "connect", self._configure_connection)
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def _configure_connection(self, connection: Any, _: Any) -> None:
        self.policy.configure_connection(connection)

    def migrate(self) -> None:
        config = Config()
        config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
        with self.engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

    @contextmanager
    def transaction(self) -> Iterator[Session]:
        with self.sessions() as session:
            self.policy.begin_write(session)
            try:
                yield session
                session.commit()
            except BaseException:
                session.rollback()
                raise

    def close(self) -> None:
        self.engine.dispose()


def audit(session: Session, event_name: str, resource_id: str, **details: Any) -> None:
    # Callers pass identifiers/statuses only, never prompts, credentials, or memory text.
    session.add(AuditEvent(event=event_name, resource_id=resource_id, details=details))
