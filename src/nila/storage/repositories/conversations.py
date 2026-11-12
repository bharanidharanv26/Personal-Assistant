import time
from dataclasses import dataclass

from sqlalchemy import select

from nila.core.schemas import MessageView
from nila.storage.database import Database, audit
from nila.storage.models import Conversation, Episode, Message
from nila.storage.queries import require


@dataclass(frozen=True)
class ConversationTurn:
    role: str
    content: str
    context_refs: dict[str, float]


class ConversationRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def open(self, conversation_id: str | None) -> str:
        with self.db.transaction() as session:
            if conversation_id is None:
                conversation = Conversation()
                session.add(conversation)
                session.flush()
                return conversation.id
            return require(session, Conversation, conversation_id).id

    def begin_turn(
        self, conversation_id: str, message: str, provider: str,
        context_refs: dict[str, float],
    ) -> str:
        with self.db.transaction() as session:
            episode = Episode(
                kind="chat", resource_id=conversation_id, status="running",
                provider=provider, context_refs=context_refs,
            )
            session.add(episode)
            session.flush()
            session.add(Message(
                conversation_id=conversation_id, episode_id=episode.id,
                role="user", content=message, provider=provider,
            ))
            return episode.id

    def fail_turn(self, conversation_id: str, episode_id: str) -> None:
        with self.db.transaction() as session:
            episode = require(session, Episode, episode_id)
            episode.status = "failed"
            episode.completed_at = time.time()
            audit(session, "chat_failed", conversation_id, episode_id=episode_id)

    def complete_turn(
        self, conversation_id: str, episode_id: str, reply: str, provider: str
    ) -> str:
        with self.db.transaction() as session:
            assistant = Message(
                conversation_id=conversation_id, episode_id=episode_id,
                role="assistant", content=reply, provider=provider,
            )
            session.add(assistant)
            session.flush()
            episode = require(session, Episode, episode_id)
            episode.status = "succeeded"
            episode.completed_at = time.time()
            episode.outcome = {"message_id": assistant.id}
            audit(session, "chat_completed", conversation_id, message_id=assistant.id)
            return assistant.id

    def history(self, conversation_id: str, limit: int = 100) -> list[MessageView]:
        with self.db.sessions() as session:
            require(session, Conversation, conversation_id)
            messages = list(session.scalars(
                select(Message).where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.desc()).limit(limit)
            ))
            return [MessageView.model_validate(message) for message in reversed(messages)]

    def recent_turns(
        self, conversation_id: str, provider: str, limit: int = 12
    ) -> list[ConversationTurn]:
        with self.db.sessions() as session:
            rows = session.execute(
                select(Message, Episode)
                .join(Episode, Message.episode_id == Episode.id)
                .where(
                    Message.conversation_id == conversation_id,
                    Message.provider == provider,
                    Episode.status == "succeeded",
                )
                .order_by(Message.created_at.desc())
                .limit(limit)
            )
            return [
                ConversationTurn(
                    role=message.role,
                    content=message.content,
                    context_refs=episode.context_refs,
                )
                for message, episode in reversed(list(rows))
            ]
