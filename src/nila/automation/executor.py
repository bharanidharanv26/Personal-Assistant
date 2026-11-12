import asyncio
from typing import Any

from nila.automation.tools import ToolRegistry
from nila.core.config import Settings
from nila.core.errors import DomainError
from nila.core.schemas import ActionView, TaskView
from nila.storage.repositories import ExecutionRepository, TaskRepository


class Executor:
    def __init__(
        self, settings: Settings, tools: ToolRegistry, executions: ExecutionRepository,
        tasks: TaskRepository,
    ) -> None:
        self.settings = settings
        self.tools = tools
        self.executions = executions
        self.tasks = tasks

    def get_action(self, action_id: str) -> ActionView:
        return self.executions.get_action(action_id)

    async def execute(self, action_id: str) -> ActionView:
        outcome = self.executions.claim(
            action_id,
            timeout_seconds=self.settings.task_timeout_seconds,
            validate=self.tools.validate,
        )
        if isinstance(outcome, DomainError):
            raise outcome
        claim = outcome
        result: dict[str, Any] | None = None
        error: str | None = None
        status = "succeeded"
        try:
            result = await asyncio.wait_for(
                self.tools.execute(claim.tool, claim.arguments), timeout=claim.remaining
            )
        except TimeoutError:
            status = "interrupted"
            error = "Tool timed out; outcome may be unknown. Review before creating a new plan."
        except Exception:
            status = "failed"
            error = "Tool execution failed. Review before creating a new plan."
        # Cancellation/shutdown leaves 'running' durable; startup recovery marks it interrupted.
        view = self.executions.complete(
            claim.action_id, claim.task_id, claim.episode_id,
            status=status, result=result, error=error,
        )
        if error is not None:
            raise DomainError(504 if status == "interrupted" else 502, error, action_id)
        return view

    async def run_task(self, task_id: str) -> TaskView:
        action_ids = self.executions.executable_action_ids(task_id)
        for action_id in action_ids:
            await self.execute(action_id)
        return self.tasks.get(task_id)
