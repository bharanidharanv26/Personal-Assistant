from nila.core.schemas import MemoryCreate, MemoryUpdate, MemoryView
from nila.storage.repositories import MemoryRepository


class MemoryService:
    def __init__(self, repository: MemoryRepository) -> None:
        self.repository = repository

    def create(self, request: MemoryCreate) -> MemoryView:
        return self.repository.create(request)

    def update(self, memory_id: str, request: MemoryUpdate) -> MemoryView:
        return self.repository.update(memory_id, request)

    def delete(self, memory_id: str) -> None:
        self.repository.delete(memory_id)

    def list_memories(self, limit: int | None = 100) -> list[MemoryView]:
        return self.repository.list_memories(limit)

    def search(self, query: str, limit: int = 5, *, remote: bool = False) -> list[MemoryView]:
        return self.repository.search(query, limit, remote=remote)
