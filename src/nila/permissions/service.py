import secrets
import time

from sqlalchemy import select

from nila.automation.tools import action_digest
from nila.core.config import Settings
from nila.core.errors import DomainError
from nila.core.schemas import ApprovalView, ConsentRequest, ConsentView
from nila.storage.database import Database, audit
from nila.storage.models import Action, Approval, Consent, Task
from nila.storage.queries import TERMINAL_TASK_STATES, require


class PermissionService:
    def __init__(self, db: Database, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    def approve(self, action_id: str, digest: str) -> ApprovalView:
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
            approval.expires_at = time.time() + self.settings.approval_ttl_seconds
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

    def grant_consent(self, request: ConsentRequest) -> ConsentView:
        with self.db.transaction() as session:
            consent = Consent(
                scope=request.scope, expires_at=time.time() + request.lifetime_seconds
            )
            session.add(consent)
            session.flush()
            audit(session, "consent_granted", consent.id, scope=consent.scope)
            return ConsentView.model_validate(consent)

    def list_consents(self, limit: int = 100) -> list[ConsentView]:
        with self.db.sessions() as session:
            return [ConsentView.model_validate(consent) for consent in session.scalars(
                select(Consent).order_by(Consent.created_at.desc()).limit(limit)
            )]

    def revoke_consent(self, consent_id: str) -> ConsentView:
        with self.db.transaction() as session:
            consent = require(session, Consent, consent_id)
            if consent.revoked_at is None:
                consent.revoked_at = time.time()
                audit(session, "consent_revoked", consent_id)
            return ConsentView.model_validate(consent)
