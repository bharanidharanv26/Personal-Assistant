import secrets
import time

from sqlalchemy import select

from nila.core.errors import DomainError
from nila.core.integrity import action_digest
from nila.core.schemas import ApprovalView
from nila.storage.database import Database, audit
from nila.storage.models import Action, Approval, Task
from nila.storage.queries import TERMINAL_TASK_STATES, require


class ApprovalRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def approve(self, action_id: str, digest: str, ttl_seconds: int) -> ApprovalView:
        with self.db.transaction() as session:
            action = require(session, Action, action_id)
            task = require(session, Task, action.task_id)
            approval = session.scalar(select(Approval).where(Approval.action_id == action_id))
            if (
                action.status == "approved" and approval is not None
                and approval.consumed_at is None and approval.expires_at <= time.time()
            ):
                action.status = "expired"
            if task.status in TERMINAL_TASK_STATES or action.status not in {"proposed", "expired"}:
                raise DomainError(409, "Action is not awaiting approval", action_id)
            current = action_digest(
                task.id, task.revision, action.position, action.tool, action.arguments
            )
            if not secrets.compare_digest(current, digest) or current != action.digest:
                raise DomainError(409, "Action changed; the preview is no longer valid", action_id)
            if approval is None:
                approval = Approval(action_id=action_id, digest=digest, expires_at=0)
                session.add(approval)
            if approval.consumed_at is not None:
                raise DomainError(409, "Approval has already been consumed", action_id)
            approval.digest = digest
            approval.expires_at = time.time() + ttl_seconds
            action.status = "approved"
            session.flush()
            actions = list(session.scalars(select(Action).where(Action.task_id == task.id)))
            if all(item.status in {"approved", "succeeded"} for item in actions):
                task.status = "ready"
            audit(session, "action_approved", action_id, digest=digest)
            return ApprovalView.model_validate(approval)

    def refuse(self, action_id: str, *, revoke: bool = False) -> None:
        with self.db.transaction() as session:
            action = require(session, Action, action_id)
            task = require(session, Task, action.task_id)
            allowed = {"approved"} if revoke else {"proposed", "expired"}
            if action.status not in allowed or task.status in TERMINAL_TASK_STATES:
                raise DomainError(
                    409, "Action cannot be denied or revoked in this state", action_id
                )
            action.status = "revoked" if revoke else "denied"
            task.status = "cancelled"
            for other in session.scalars(select(Action).where(Action.task_id == task.id)):
                if other.id != action_id and other.status in {"proposed", "approved", "expired"}:
                    other.status = "cancelled"
            audit(session, "action_revoked" if revoke else "action_denied", action_id)
