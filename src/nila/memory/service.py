import re
import time

from sqlalchemy import select, text

from nila.core.schemas import MemoryCreate, MemoryUpdate, MemoryView
from nila.storage.database import Database, audit
from nila.storage.models import Memory
from nila.storage.queries import require


class MemoryService:
    def __init__(self, database: Database) -> None:
        self.db = database

    def create(self, request: MemoryCreate) -> MemoryView:
        with self.db.transaction() as session:
            memory = Memory(**request.model_dump(), source="user")
            session.add(memory)
            session.flush()
            audit(session, "memory_created", memory.id, allow_remote=memory.allow_remote)
            return MemoryView.model_validate(memory)

    def update(self, memory_id: str, request: MemoryUpdate) -> MemoryView:
        with self.db.transaction() as session:
            memory = require(session, Memory, memory_id)
            memory.content = request.content
            memory.kind = request.kind
            memory.allow_remote = request.allow_remote
            memory.updated_at = time.time()
            audit(session, "memory_updated", memory.id, allow_remote=memory.allow_remote)
            return MemoryView.model_validate(memory)

    def delete(self, memory_id: str) -> None:
        with self.db.transaction() as session:
            session.delete(require(session, Memory, memory_id))
            audit(session, "memory_deleted", memory_id)

    def list_memories(self, limit: int | None = 100) -> list[MemoryView]:
        with self.db.sessions() as session:
            query = select(Memory).order_by(Memory.created_at.desc())
            if limit is not None:
                query = query.limit(limit)
            return [MemoryView.model_validate(row) for row in session.scalars(query)]

    def search(self, query: str, limit: int = 5, *, remote: bool = False) -> list[MemoryView]:
        # Users supply plain text, never FTS operators. Bind the quoted terms as data.
        terms = list(dict.fromkeys(re.findall(r"\w+", query, flags=re.UNICODE)))[:32]
        if not terms:
            return []
        match = " OR ".join(f'"{term}"' for term in terms)
        with self.db.sessions() as session:
            ids = session.scalars(
                text(
                    "SELECT memory_id FROM memory_fts JOIN memories ON memories.id = memory_id "
                    "WHERE memory_fts MATCH :query AND (:remote = 0 OR memories.allow_remote = 1) "
                    "ORDER BY bm25(memory_fts), memories.created_at DESC LIMIT :limit"
                ),
                {"query": match, "limit": limit, "remote": int(remote)},
            )
            return [MemoryView.model_validate(require(session, Memory, row_id)) for row_id in ids]
