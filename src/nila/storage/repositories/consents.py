import time

from sqlalchemy import select

from nila.core.schemas import ConsentRequest, ConsentView
from nila.storage.database import Database, audit
from nila.storage.models import Consent
from nila.storage.queries import require


class ConsentRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def grant(self, request: ConsentRequest) -> ConsentView:
        with self.db.transaction() as session:
            consent = Consent(
                scope=request.scope, expires_at=time.time() + request.lifetime_seconds
            )
            session.add(consent)
            session.flush()
            audit(session, "consent_granted", consent.id, scope=consent.scope)
            return ConsentView.model_validate(consent)

    def list(self, limit: int = 100) -> list[ConsentView]:
        with self.db.sessions() as session:
            return [ConsentView.model_validate(consent) for consent in session.scalars(
                select(Consent).order_by(Consent.created_at.desc()).limit(limit)
            )]

    def revoke(self, consent_id: str) -> ConsentView:
        with self.db.transaction() as session:
            consent = require(session, Consent, consent_id)
            if consent.revoked_at is None:
                consent.revoked_at = time.time()
                audit(session, "consent_revoked", consent_id)
            return ConsentView.model_validate(consent)
