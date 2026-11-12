import json

from nila.core.runtime import build_services
from nila.core.schemas import ChatRequest, MemoryCreate, MemoryUpdate
from nila.llm.providers import DemoProvider


class RecordingProvider(DemoProvider):
    name = "recording"
    remote = True

    def __init__(self):
        self.prompts = []

    async def chat(self, prompt):
        self.prompts.append(prompt)
        return "A reply that may repeat information from the supplied context."


async def test_hosted_context_only_includes_opted_in_memories(config):
    provider = RecordingProvider()
    services = build_services(config, provider=provider)
    try:
        services.memory.create(MemoryCreate(content="tea local-secret-only"))
        shared = services.memory.create(MemoryCreate(content="tea jasmine", allow_remote=True))
        response = await services.chat.chat(ChatRequest(message="tea"))
        payload = json.dumps(provider.prompts[-1].messages)
        assert "local-secret-only" not in payload
        assert "jasmine" in payload
        assert response.memory_ids == [shared.id]
    finally:
        await services.close()


async def test_deleted_memory_invalidates_transitive_conversation_context(config):
    provider = RecordingProvider()
    services = build_services(config, provider=provider)
    try:
        memory = services.memory.create(MemoryCreate(content="jasmine tea", allow_remote=True))
        first = await services.chat.chat(ChatRequest(message="tea"))
        second = await services.chat.chat(ChatRequest(
            message="Continue", conversation_id=first.conversation_id
        ))
        assert second.memory_ids == [memory.id]  # Provenance inherited from history.
        services.memory.delete(memory.id)
        third = await services.chat.chat(ChatRequest(
            message="Continue", conversation_id=first.conversation_id
        ))
        assert third.memory_ids == []
        assert len(provider.prompts[-1].messages) == 2  # System + current request only.
    finally:
        await services.close()


async def test_revoking_sharing_excludes_prior_assistant_context(config):
    provider = RecordingProvider()
    services = build_services(config, provider=provider)
    try:
        memory = services.memory.create(MemoryCreate(content="tea jasmine", allow_remote=True))
        first = await services.chat.chat(ChatRequest(message="tea"))
        services.memory.update(memory.id, MemoryUpdate(content="tea jasmine", allow_remote=False))
        await services.chat.chat(ChatRequest(message="tea", conversation_id=first.conversation_id))
        assert "jasmine" not in json.dumps(provider.prompts[-1].messages)
        assert len(provider.prompts[-1].messages) == 2
    finally:
        await services.close()


async def test_context_budget_trims_memory_before_provider_call(config):
    provider = RecordingProvider()
    services = build_services(config, provider=provider)
    try:
        for _ in range(5):
            services.memory.create(MemoryCreate(
                content="tea " + "x" * 3996, allow_remote=True
            ))
        await services.chat.chat(ChatRequest(message="tea " + "z" * 7996))
        assert len(json.dumps(provider.prompts[-1].messages, ensure_ascii=False)) <= (
            config.max_context_chars
        )
        assert len(provider.prompts[-1].memory_refs) < 5
    finally:
        await services.close()
