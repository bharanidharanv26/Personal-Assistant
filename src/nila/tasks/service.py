import asyncio
import logging
import time

from sqlalchemy import select

from nila.agent.context import ContextBuilder
from nila.automation.tools import ToolRegistry, action_digest
from nila.core.config import Settings
from nila.core.errors import DomainError
from nila.core.schemas import PlanDraft, TaskRequest, TaskView
from nila.llm.base import Provider
from nila.storage.database import Database, audit
from nila.storage.models import Action, Episode, Task
from nila.storage.queries import TERMINAL_TASK_STATES, require, task_view

logger = logging.getLogger(__name__)


class TaskService:
    def __init__(
        self, db: Database, settings: Settings, provider: Provider,
        context: ContextBuilder, tools: ToolRegistry,
    ) -> None:
        self.db = db
        self.settings = settings
        self.provider = provider
        self.context = context
        self.tools = tools

    async def plan(self, request: TaskRequest) -> TaskView:
        prompt = self.context.build(request.objective, planning=True)
        with self.db.transaction() as session:
            task = Task(
                objective=request.objective, title="Planning", status="planning",
                provider=self.provider.name,
            )
            session.add(task)
            session.flush()
            task_id = task.id
            episode = Episode(
                kind="plan", resource_id=task_id, status="running",
                provider=self.provider.name, context_refs=prompt.memory_refs,
            )
            session.add(episode)
            session.flush()
            episode_id = episode.id
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
            with self.db.transaction() as session:
                task = require(session, Task, task_id)
                if task.status == "planning":
                    task.status = "failed"
                    task.error = "Planning failed or exceeded configured limits"
                episode = require(session, Episode, episode_id)
                episode.status = "failed"
                episode.completed_at = time.time()
                audit(session, "planning_failed", task_id)
            raise DomainError(
                502, "Planning failed or exceeded configured limits", task_id
            ) from exc
        with self.db.transaction() as session:
            task = require(session, Task, task_id)
            episode = require(session, Episode, episode_id)
            episode.completed_at = time.time()
            if task.status == "cancelled":
                episode.status = "cancelled"
                return task_view(session, task)
            task.title = plan.title
            task.status = "awaiting_approval"
            for position, step in enumerate(plan.steps, start=1):
                arguments = step.arguments.model_dump()
                session.add(Action(
                    task_id=task_id, position=position, tool=step.tool, arguments=arguments,
                    digest=action_digest(task_id, task.revision, position, step.tool, arguments),
                ))
            session.flush()
            episode.status = "succeeded"
            episode.outcome = {"step_count": len(plan.steps)}
            audit(session, "task_planned", task_id, step_count=len(plan.steps))
            return task_view(session, task)

    def get(self, task_id: str) -> TaskView:
        with self.db.sessions() as session:
            return task_view(session, require(session, Task, task_id))

    def list(self, limit: int = 100) -> list[TaskView]:
        with self.db.sessions() as session:
            return [task_view(session, task) for task in session.scalars(
                select(Task).order_by(Task.created_at.desc()).limit(limit)
            )]

    def cancel(self, task_id: str) -> TaskView:
        with self.db.transaction() as session:
            task = require(session, Task, task_id)
            if task.status in TERMINAL_TASK_STATES:
                raise DomainError(409, "Task is already terminal", task_id)
            task.status = "cancelled"
            for action in session.scalars(select(Action).where(Action.task_id == task_id)):
                if action.status in {"proposed", "approved", "expired"}:
                    action.status = "cancelled"
            audit(session, "task_cancelled", task_id)
            session.flush()
            return task_view(session, task)
