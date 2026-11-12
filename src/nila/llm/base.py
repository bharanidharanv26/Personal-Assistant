from dataclasses import dataclass
from typing import Literal, Protocol, TypedDict

from nila.core.schemas import PlanDraft


class LLMMessage(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class Prompt:
    messages: list[LLMMessage]
    memory_refs: dict[str, float]
    request: str


class Provider(Protocol):
    name: str
    remote: bool

    async def chat(self, prompt: Prompt) -> str: ...

    async def plan(self, prompt: Prompt) -> PlanDraft: ...

    async def close(self) -> None: ...
