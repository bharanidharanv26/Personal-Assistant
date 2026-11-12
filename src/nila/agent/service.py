import asyncio
import logging
import time

from sqlalchemy import select

from nila.agent.context import ContextBuilder
from nila.core.config import Settings
from nila.core.errors import DomainError
from nila.core.schemas import ChatRequest, ChatResponse, MessageView
from nila.llm.base import Provider
from nila.storage.database import Database, audit
from nila.storage.models import Conversation, Episode, Message
from nila.storage.queries import require

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(
        self, db: Database, settings: Settings, provider: Provider, context: ContextBuilder
    ) -> None:
        self.db = db
        self.settings = settings
        self.provider = provider
        self.context = context
        self._busy_conversations: set[str] = set()

    async def chat(self, request: ChatRequest) -> ChatResponse:
        with self.db.transaction() as session:
            if request.conversation_id is None:
                conversation = Conversation()
                session.add(conversation)
                session.flush()
            else:
                conversation = require(session, Conversation, request.conversation_id)
            conversation_id = conversation.id
        if conversation_id in self._busy_conversations:
            raise DomainError(409, "This conversation already has a response in progress")
        self._busy_conversations.add(conversation_id)
        try:
            return await self._respond(request.message, conversation_id)
        finally:
            self._busy_conversations.discard(conversation_id)

    async def _respond(self, message: str, conversation_id: str) -> ChatResponse:
        prompt = self.context.build(message, conversation_id=conversation_id)
        with self.db.transaction() as session:
            episode = Episode(
                kind="chat", resource_id=conversation_id, status="running",
                provider=self.provider.name, context_refs=prompt.memory_refs,
            )
            session.add(episode)
            session.flush()
            episode_id = episode.id
            session.add(Message(
                conversation_id=conversation_id, episode_id=episode_id,
                role="user", content=message, provider=self.provider.name,
            ))
        try:
            reply = await asyncio.wait_for(
                self.provider.chat(prompt), timeout=self.settings.llm_timeout_seconds
            )
            if not reply.strip():
                raise ValueError("Empty response")
        except Exception as exc:
            logger.warning("Chat provider failed (%s)", type(exc).__name__)
            with self.db.transaction() as session:
                episode = require(session, Episode, episode_id)
                episode.status = "failed"
                episode.completed_at = time.time()
                audit(session, "chat_failed", conversation_id, episode_id=episode_id)
            raise DomainError(502, "LLM request failed or timed out", conversation_id) from exc
        with self.db.transaction() as session:
            assistant = Message(
                conversation_id=conversation_id, episode_id=episode_id,
                role="assistant", content=reply, provider=self.provider.name,
            )
            session.add(assistant)
            session.flush()
            episode = require(session, Episode, episode_id)
            episode.status = "succeeded"
            episode.completed_at = time.time()
            episode.outcome = {"message_id": assistant.id}
            audit(session, "chat_completed", conversation_id, message_id=assistant.id)
            return ChatResponse(
                conversation_id=conversation_id, message_id=assistant.id, reply=reply,
                provider=self.provider.name, memory_ids=list(prompt.memory_refs),
            )

    def history(self, conversation_id: str, limit: int = 100) -> list[MessageView]:
        with self.db.sessions() as session:
            require(session, Conversation, conversation_id)
            messages = list(session.scalars(
                select(Message).where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.desc()).limit(limit)
            ))
            return [MessageView.model_validate(message) for message in reversed(messages)]
