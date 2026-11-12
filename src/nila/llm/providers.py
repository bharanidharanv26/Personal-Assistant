import json
from typing import cast

from openai import AsyncOpenAI
from openai.types.responses import ResponseInputParam

from nila.core.config import Settings
from nila.core.credentials import openai_key
from nila.core.schemas import DryRunArguments, PlanDraft, PlanStep
from nila.llm.base import Prompt, Provider


class DemoProvider:
    name = "demo"
    remote = False

    async def chat(self, prompt: Prompt) -> str:
        data = json.loads(prompt.messages[-1]["content"])
        memories = data["reference_memory"]
        context = "\n".join(f"- {entry['content']}" for entry in memories)
        if not context:
            context = "No matching saved memories."
        return (
            f"[OFFLINE DEMO — no model reasoning]\nRequest: {prompt.request}\n"
            f"Retrieved memory:\n{context}"
        )

    async def plan(self, prompt: Prompt) -> PlanDraft:
        return PlanDraft(
            title=f"Demo: {prompt.request[:190]}",
            steps=[
                PlanStep(
                    tool="dry_run",
                    arguments=DryRunArguments(description=prompt.request[:2000]),
                )
            ],
        )

    async def close(self) -> None:
        pass


class OpenAIProvider:
    name = "openai"
    remote = True

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = AsyncOpenAI(
            api_key=openai_key(settings),
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
        )

    async def chat(self, prompt: Prompt) -> str:
        response = await self.client.responses.create(
            model=self.settings.openai_model or "",
            input=cast(ResponseInputParam, prompt.messages),
            max_output_tokens=self.settings.max_output_tokens,
            store=False,
        )
        if not response.output_text.strip() or response.status != "completed":
            raise ValueError("Provider returned an incomplete or empty response")
        return response.output_text

    async def plan(self, prompt: Prompt) -> PlanDraft:
        response = await self.client.responses.parse(
            model=self.settings.openai_model or "",
            input=cast(ResponseInputParam, prompt.messages),
            text_format=PlanDraft,
            max_output_tokens=self.settings.max_output_tokens,
            store=False,
        )
        if response.output_parsed is None or response.status != "completed":
            raise ValueError("Provider did not return a complete structured plan")
        return response.output_parsed

    async def close(self) -> None:
        await self.client.close()


def create_provider(settings: Settings) -> Provider:
    return OpenAIProvider(settings) if settings.llm_provider == "openai" else DemoProvider()
