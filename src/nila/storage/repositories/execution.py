import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from nila.core.errors import DomainError
from nila.core.integrity import action_digest
from nila.core.schemas import ActionView
from nila.storage.database import Database, audit
from nila.storage.models import Action, Approval, Episode, Task
from nila.storage.queries import TERMINAL_TASK_STATES, require

ToolValidator = Callable[[str, dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class ActionClaim:
    action_id: str
    task_id: str
    episode_id: str
    tool: str
    arguments: dict[str, Any]
    remaining: float


class ExecutionRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def get_action(self, action_id: str) -> ActionView:
        with self.db.sessions() as session:
            return ActionView.model_validate(require(session, Action, action_id))

    def claim(
        self, action_id: str, *, timeout_seconds: float, validate: ToolValidator
    ) -> ActionClaim | DomainError:
        failure: DomainError | None = None
        with self.db.transaction() as session:
            action = require(session, Action, action_id)
            task = require(session, Task, action.task_id)
            task_id = task.id
            if task.status in TERMINAL_TASK_STATES:
                raise DomainError(409, "Task is terminal; create a new plan to continue", task_id)
            if action.status != "approved":
                raise DomainError(409, "Action needs an unused approval", action_id)
            previous = session.scalars(select(Action).where(
                Action.task_id == task_id, Action.position < action.position
            ))
            if any(item.status != "succeeded" for item in previous):
                raise DomainError(409, "Earlier steps must succeed first", action_id)
            approval = session.scalar(select(Approval).where(Approval.action_id == action_id))
            if approval is None or approval.consumed_at is not None:
                raise DomainError(409, "Action needs an unused approval", action_id)
            now = time.time()
            digest = action_digest(
                task_id, task.revision, action.position, action.tool, action.arguments
            )
            remaining = timeout_seconds
            if task.started_at is not None:
                remaining -= now - task.started_at
            if approval.expires_at <= now:
                action.status = "expired"
                task.status = "awaiting_approval"
                audit(session, "approval_expired", action_id)
                failure = DomainError(409, "Approval expired; review and approve again", action_id)
            elif not secrets.compare_digest(approval.digest, digest) or action.digest != digest:
                action.status = "invalid"
                task.status = "failed"
                task.error = "Approved action was altered"
                audit(session, "approval_invalidated", action_id)
                failure = DomainError(
                    409, "Action changed after approval; create a new plan", action_id
                )
            elif remaining <= 0:
                task.status = "interrupted"
                action.status = "interrupted"
                task.error = "Task execution deadline exceeded"
                audit(session, "task_deadline_exceeded", task_id)
                failure = DomainError(409, "Task execution deadline exceeded", task_id)
            else:
                try:
                    arguments = validate(action.tool, action.arguments)
                except ValueError as exc:
                    raise DomainError(
                        409, "Tool or arguments are no longer valid", action_id
                    ) from exc
                tool = action.tool
                approval.consumed_at = now
                action.status = "running"
                task.status = "running"
                task.started_at = task.started_at or now
                episode = Episode(
                    kind="action", resource_id=action_id, status="running", provider="dry_run"
                )
                session.add(episode)
                session.flush()
                episode_id = episode.id
                audit(session, "action_started", action_id, digest=digest)
                return ActionClaim(
                    action_id=action_id, task_id=task_id, episode_id=episode_id,
                    tool=tool, arguments=arguments, remaining=remaining,
                )
        if failure is None:
            raise RuntimeError("Execution claim ended without a result")
        return failure

    def complete(
        self, action_id: str, task_id: str, episode_id: str, *, status: str,
        result: dict[str, Any] | None, error: str | None,
    ) -> ActionView:
        with self.db.transaction() as session:
            action = require(session, Action, action_id)
            task = require(session, Task, task_id)
            episode = require(session, Episode, episode_id)
            if action.status != "running":
                raise DomainError(
                    409, "Execution is no longer current; result was not recorded", action_id
                )
            action.status = status
            action.result = result
            action.error = error
            episode.status = status
            episode.completed_at = time.time()
            episode.outcome = {"simulated": True, "status": status}
            session.flush()
            if task.status != "cancelled":
                if status != "succeeded":
                    task.status = status
                    task.error = error
                else:
                    actions = list(session.scalars(select(Action).where(Action.task_id == task_id)))
                    if all(item.status == "succeeded" for item in actions):
                        task.status = "succeeded"
                    elif all(item.status in {"approved", "succeeded"} for item in actions):
                        task.status = "ready"
                    else:
                        task.status = "awaiting_approval"
            audit(session, "action_finished", action_id, status=status)
            return ActionView.model_validate(action)

    def executable_action_ids(self, task_id: str) -> list[str]:
        with self.db.sessions() as session:
            task = require(session, Task, task_id)
            if task.status in TERMINAL_TASK_STATES or task.status == "planning":
                raise DomainError(409, "Task is not executable", task_id)
            actions = list(session.scalars(
                select(Action).where(Action.task_id == task_id).order_by(Action.position)
            ))
            if not actions or any(item.status not in {"approved", "succeeded"} for item in actions):
                raise DomainError(
                    409, "Approve every remaining action before running the task", task_id
                )
            return [item.id for item in actions if item.status != "succeeded"]

    def recover_interrupted(self) -> None:
        with self.db.transaction() as session:
            for task in session.scalars(
                select(Task).where(Task.status.in_(["planning", "running"]))
            ):
                task.status = "interrupted"
                task.error = "Service stopped during processing; review and create a new plan"
                audit(session, "task_recovered_as_interrupted", task.id)
            for action in session.scalars(select(Action).where(Action.status == "running")):
                action.status = "interrupted"
                action.error = "Previous execution outcome is unknown; automatic replay is blocked"
                audit(session, "action_recovered_as_interrupted", action.id)
            for episode in session.scalars(select(Episode).where(Episode.status == "running")):
                episode.status = "interrupted"
                episode.completed_at = time.time()
