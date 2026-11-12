import time

from sqlalchemy import select

from nila.core.errors import DomainError
from nila.core.integrity import action_digest
from nila.core.schemas import PlanDraft, TaskView
from nila.storage.database import Database, audit
from nila.storage.models import Action, Episode, Task
from nila.storage.queries import TERMINAL_TASK_STATES, require, task_view


class TaskRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def start_plan(
        self, objective: str, provider: str, context_refs: dict[str, float]
    ) -> tuple[str, str]:
        with self.db.transaction() as session:
            task = Task(
                objective=objective, title="Planning", status="planning", provider=provider,
            )
            session.add(task)
            session.flush()
            episode = Episode(
                kind="plan", resource_id=task.id, status="running",
                provider=provider, context_refs=context_refs,
            )
            session.add(episode)
            session.flush()
            return task.id, episode.id

    def fail_plan(self, task_id: str, episode_id: str, error: str) -> None:
        with self.db.transaction() as session:
            task = require(session, Task, task_id)
            if task.status == "planning":
                task.status = "failed"
                task.error = error
            episode = require(session, Episode, episode_id)
            episode.status = "failed"
            episode.completed_at = time.time()
            audit(session, "planning_failed", task_id)

    def complete_plan(self, task_id: str, episode_id: str, plan: PlanDraft) -> TaskView:
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
