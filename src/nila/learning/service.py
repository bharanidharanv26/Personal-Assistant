from typing import Any

from nila.core.schemas import FeedbackRequest, FeedbackView
from nila.storage.repositories import FeedbackRepository


class LearningService:
    def __init__(self, repository: FeedbackRepository) -> None:
        self.repository = repository

    def feedback(self, request: FeedbackRequest) -> FeedbackView:
        return self.repository.record(request)

    def evaluation(self) -> dict[str, Any]:
        return self.repository.evaluation()
