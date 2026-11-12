from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MemoryCreate(Command):
    content: str = Field(min_length=1, max_length=4000)
    kind: Literal["fact", "preference"] = "fact"
    allow_remote: bool = False


class MemoryUpdate(MemoryCreate):
    pass


class ChatRequest(Command):
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=64)


class TaskRequest(Command):
    objective: str = Field(min_length=1, max_length=4000)


class DryRunArguments(Command):
    description: str = Field(min_length=1, max_length=2000)


class PlanStep(Command):
    tool: Literal["dry_run"]
    arguments: DryRunArguments


class PlanDraft(Command):
    title: str = Field(min_length=1, max_length=200)
    steps: list[PlanStep] = Field(min_length=1, max_length=10)


class ApprovalRequest(Command):
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class ConsentRequest(Command):
    scope: Literal["manual_observation"] = "manual_observation"
    lifetime_seconds: int = Field(default=3600, ge=10, le=86400)


class ObservationRequest(Command):
    consent_id: str = Field(min_length=1, max_length=64)
    content: str = Field(min_length=1, max_length=2000)


class FeedbackRequest(Command):
    target_type: Literal["message", "task", "action"]
    target_id: str = Field(min_length=1, max_length=64)
    rating: Literal[-1, 1]
    correction: str | None = Field(default=None, min_length=1, max_length=2000)


class Record(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: float


class MemoryView(Record):
    content: str
    kind: str
    source: str
    allow_remote: bool
    updated_at: float


class ActionView(Record):
    task_id: str
    position: int
    tool: str
    arguments: dict[str, Any]
    digest: str
    status: str
    result: dict[str, Any] | None
    error: str | None


class TaskView(Record):
    objective: str
    title: str
    status: str
    provider: str
    revision: int
    started_at: float | None
    error: str | None
    actions: list[ActionView] = Field(default_factory=list)


class ApprovalView(Record):
    action_id: str
    digest: str
    expires_at: float
    consumed_at: float | None


class ConsentView(Record):
    scope: str
    expires_at: float
    revoked_at: float | None


class ObservationView(Record):
    consent_id: str
    content: str


class FeedbackView(Record):
    target_type: str
    target_id: str
    rating: int
    correction: str | None


class MessageView(Record):
    conversation_id: str
    role: str
    content: str
    provider: str


class ChatResponse(BaseModel):
    conversation_id: str
    message_id: str
    reply: str
    provider: str
    memory_ids: list[str]
