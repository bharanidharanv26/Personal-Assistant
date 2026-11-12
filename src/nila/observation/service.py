from nila.core.schemas import ObservationRequest, ObservationView
from nila.storage.repositories import ObservationRepository


class ObservationService:
    def __init__(self, observations: ObservationRepository) -> None:
        self.observations = observations

    def create(self, request: ObservationRequest) -> ObservationView:
        return self.observations.create(request)

    def list(self, limit: int = 100) -> list[ObservationView]:
        return self.observations.list(limit)

    def delete(self, observation_id: str) -> None:
        self.observations.delete(observation_id)
