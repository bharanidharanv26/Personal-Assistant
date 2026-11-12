import asyncio
import logging

from nila.agent.context import ContextBuilder
from nila.automation.tools import ToolRegistry
from nila.core.config import Settings
from nila.core.errors import DomainError
from nila.core.schemas import PlanDraft, TaskRequest, TaskView
from nila.llm.base import Provider
from nila.storage.repositories import TaskRepository

logger = logging.getLogger(__name__)


class TaskService:
    def __init__(
        self, settings: Settings, provider: Provider, context: ContextBuilder,
        tools: ToolRegistry, tasks: TaskRepository,
    ) -> None:
        self.settings = settings
        self.provider = provider
        self.context = context
        self.tools = tools
        self.tasks = tasks

    async def plan(self, request: TaskRequest) -> TaskView:
        prompt = self.context.build(request.objective, planning=True)
        task_id, episode_id = self.tasks.start_plan(
            request.objective, self.provider.name, prompt.memory_refs
        )
        try:
            proposed = await asyncio.wait_for(
                self.provider.plan(prompt), timeout=self.settings.llm_timeout_seconds
            )
            plan = PlanDraft.model_validate(proposed.model_dump())
            if len(plan.steps) > self.settings.max_steps:
                raise ValueError("Plan exceeds step budget")
            for step in plan.steps:
                self.tools.validate(step.tool, step.arguments.model_dump())
        except Exception as exc:
            logger.warning("Planning failed (%s)", type(exc).__name__)
            self.tasks.fail_plan(
                task_id, episode_id, "Planning failed or exceeded configured limits"
            )
            raise DomainError(
                502, "Planning failed or exceeded configured limits", task_id
            ) from exc
        return self.tasks.complete_plan(task_id, episode_id, plan)

    def get(self, task_id: str) -> TaskView:
        return self.tasks.get(task_id)

    def list(self, limit: int = 100) -> list[TaskView]:
        return self.tasks.list(limit)

    def cancel(self, task_id: str) -> TaskView:
        return self.tasks.cancel(task_id)
