import time

from sqlalchemy import select

from nila.core.errors import DomainError
from nila.core.schemas import ObservationRequest, ObservationView
from nila.storage.database import Database, audit
from nila.storage.models import Consent, Observation
from nila.storage.queries import require


class ObservationService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, request: ObservationRequest) -> ObservationView:
        with self.db.transaction() as session:
            consent = require(session, Consent, request.consent_id)
            if (
                consent.scope != "manual_observation"
                or consent.revoked_at is not None
                or consent.expires_at <= time.time()
            ):
                raise DomainError(403, "Active manual-observation consent is required")
            observation = Observation(**request.model_dump())
            session.add(observation)
            session.flush()
            audit(session, "observation_recorded", observation.id, consent_id=consent.id)
            return ObservationView.model_validate(observation)

    def list(self, limit: int = 100) -> list[ObservationView]:
        with self.db.sessions() as session:
            return [ObservationView.model_validate(row) for row in session.scalars(
                select(Observation).order_by(Observation.created_at.desc()).limit(limit)
            )]

    def delete(self, observation_id: str) -> None:
        with self.db.transaction() as session:
            session.delete(require(session, Observation, observation_id))
            audit(session, "observation_deleted", observation_id)
