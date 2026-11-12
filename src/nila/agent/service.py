import asyncio
import logging

from nila.agent.context import ContextBuilder
from nila.core.config import Settings
from nila.core.errors import DomainError
from nila.core.schemas import ChatRequest, ChatResponse, MessageView
from nila.llm.base import Provider
from nila.storage.repositories import ConversationRepository

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(
        self, settings: Settings, provider: Provider, context: ContextBuilder,
        conversations: ConversationRepository,
    ) -> None:
        self.settings = settings
        self.provider = provider
        self.context = context
        self.conversations = conversations
        self._busy_conversations: set[str] = set()

    async def chat(self, request: ChatRequest) -> ChatResponse:
        conversation_id = self.conversations.open(request.conversation_id)
        if conversation_id in self._busy_conversations:
            raise DomainError(409, "This conversation already has a response in progress")
        self._busy_conversations.add(conversation_id)
        try:
            return await self._respond(request.message, conversation_id)
        finally:
            self._busy_conversations.discard(conversation_id)

    async def _respond(self, message: str, conversation_id: str) -> ChatResponse:
        prompt = self.context.build(message, conversation_id=conversation_id)
        episode_id = self.conversations.begin_turn(
            conversation_id, message, self.provider.name, prompt.memory_refs
        )
        try:
            reply = await asyncio.wait_for(
                self.provider.chat(prompt), timeout=self.settings.llm_timeout_seconds
            )
            if not reply.strip():
                raise ValueError("Empty response")
        except Exception as exc:
            logger.warning("Chat provider failed (%s)", type(exc).__name__)
            self.conversations.fail_turn(conversation_id, episode_id)
            raise DomainError(502, "LLM request failed or timed out", conversation_id) from exc
        message_id = self.conversations.complete_turn(
            conversation_id, episode_id, reply, self.provider.name
        )
        return ChatResponse(
            conversation_id=conversation_id, message_id=message_id, reply=reply,
            provider=self.provider.name, memory_ids=list(prompt.memory_refs),
        )

    def history(self, conversation_id: str, limit: int = 100) -> list[MessageView]:
        return self.conversations.history(conversation_id, limit)
