import time
import uuid
from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    # Keep timestamp DDL stable across SQLAlchemy releases and migration history.
    type_annotation_map = {float: Float()}


class Identity:
    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    created_at: Mapped[float] = mapped_column(default=time.time)


class Memory(Identity, Base):
    __tablename__ = "memories"

    content: Mapped[str] = mapped_column(Text)
    kind: Mapped[str]
    source: Mapped[str] = mapped_column(default="user")
    allow_remote: Mapped[bool] = mapped_column(default=False)
    updated_at: Mapped[float] = mapped_column(default=time.time)


class Conversation(Identity, Base):
    __tablename__ = "conversations"


class Episode(Identity, Base):
    __tablename__ = "episodes"

    kind: Mapped[str]
    resource_id: Mapped[str]
    status: Mapped[str]
    provider: Mapped[str]
    context_refs: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    outcome: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    completed_at: Mapped[float | None]


class Message(Identity, Base):
    __tablename__ = "messages"

    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    episode_id: Mapped[str] = mapped_column(ForeignKey("episodes.id"), index=True)
    role: Mapped[str]
    content: Mapped[str] = mapped_column(Text)
    provider: Mapped[str]


class Task(Identity, Base):
    __tablename__ = "tasks"

    objective: Mapped[str] = mapped_column(Text)
    title: Mapped[str]
    status: Mapped[str]
    provider: Mapped[str]
    revision: Mapped[int] = mapped_column(default=1)
    started_at: Mapped[float | None]
    error: Mapped[str | None]


class Action(Identity, Base):
    __tablename__ = "actions"
    __table_args__ = (UniqueConstraint("task_id", "position"),)

    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), index=True)
    position: Mapped[int]
    tool: Mapped[str]
    arguments: Mapped[dict[str, Any]] = mapped_column(JSON)
    digest: Mapped[str]
    status: Mapped[str] = mapped_column(default="proposed")
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[str | None]


class Approval(Identity, Base):
    __tablename__ = "approvals"

    action_id: Mapped[str] = mapped_column(ForeignKey("actions.id"), unique=True)
    digest: Mapped[str]
    expires_at: Mapped[float]
    consumed_at: Mapped[float | None]


class Consent(Identity, Base):
    __tablename__ = "consents"

    scope: Mapped[str]
    expires_at: Mapped[float]
    revoked_at: Mapped[float | None]


class Observation(Identity, Base):
    __tablename__ = "observations"

    consent_id: Mapped[str] = mapped_column(ForeignKey("consents.id"))
    content: Mapped[str] = mapped_column(Text)


class Feedback(Identity, Base):
    __tablename__ = "feedback"
    __table_args__ = (UniqueConstraint("target_type", "target_id"),)

    target_type: Mapped[str]
    target_id: Mapped[str]
    rating: Mapped[int]
    correction: Mapped[str | None] = mapped_column(Text)


class AuditEvent(Identity, Base):
    __tablename__ = "audit_events"

    event: Mapped[str]
    resource_id: Mapped[str]
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


Index("ix_messages_conversation_created", Message.conversation_id, Message.created_at)
