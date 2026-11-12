from typing import Any

from sqlalchemy import select

from nila.storage.database import Database
from nila.storage.models import AuditEvent


class AuditRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.db.sessions() as session:
            return [
                {"id": row.id, "created_at": row.created_at, "event": row.event,
                 "resource_id": row.resource_id, "details": row.details}
                for row in session.scalars(
                    select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)
                )
            ]
