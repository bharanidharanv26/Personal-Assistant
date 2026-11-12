import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient

from nila.api.app import create_app
from nila.core.schemas import MemoryCreate, MemoryUpdate
from nila.storage.models import Base


async def test_migration_repeatability_and_model_consistency(runtime):
    runtime.db.migrate()
    with runtime.db.engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={
            "include_object": lambda obj, name, kind, reflected, other: (
                not name.startswith("memory_fts")
            )
        })
        assert compare_metadata(context, Base.metadata) == []


async def test_fts_updates_deletes_unicode_and_literal_query(runtime):
    memory = runtime.memory.create(MemoryCreate(content="jasmine tea தமிழ்"))
    assert runtime.memory.search("jasmine")[0].id == memory.id
    assert runtime.memory.search("தமிழ்")[0].id == memory.id
    assert runtime.memory.search('" OR * :') == []
    runtime.memory.update(memory.id, MemoryUpdate(content="coffee"))
    assert runtime.memory.search("jasmine") == []
    assert runtime.memory.search("coffee")[0].id == memory.id
    runtime.memory.delete(memory.id)
    assert runtime.memory.search("coffee") == []
    assert runtime.memory.list_memories() == []


def test_second_service_cannot_recover_an_active_service(config):
    with TestClient(create_app(config), base_url="http://127.0.0.1"):
        with pytest.raises(RuntimeError, match="already using this data directory"):
            with TestClient(create_app(config), base_url="http://127.0.0.1"):
                pytest.fail("A second service must not start")
