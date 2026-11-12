from typing import Any

from sqlalchemy import func, select

from nila.core.errors import DomainError
from nila.core.schemas import FeedbackRequest, FeedbackView
from nila.storage.database import Database, audit
from nila.storage.models import Action, Episode, Feedback, Message, Task
from nila.storage.queries import TERMINAL_TASK_STATES, require


class LearningService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def feedback(self, request: FeedbackRequest) -> FeedbackView:
        with self.db.transaction() as session:
            if request.target_type == "message":
                message = require(session, Message, request.target_id)
                if message.role != "assistant":
                    raise DomainError(422, "Feedback must target an assistant response")
            elif request.target_type == "task":
                task = require(session, Task, request.target_id)
                if task.status not in TERMINAL_TASK_STATES:
                    raise DomainError(409, "Task feedback requires a terminal outcome")
            else:
                action = require(session, Action, request.target_id)
                if action.status not in {"succeeded", "failed", "interrupted"}:
                    raise DomainError(409, "Action feedback requires an execution outcome")
            feedback = session.scalar(select(Feedback).where(
                Feedback.target_type == request.target_type, Feedback.target_id == request.target_id
            ))
            if feedback is None:
                feedback = Feedback(**request.model_dump())
                session.add(feedback)
            else:
                feedback.rating = request.rating
                feedback.correction = request.correction
            session.flush()
            audit(session, "feedback_recorded", feedback.id, target_type=request.target_type)
            return FeedbackView.model_validate(feedback)

    def evaluation(self) -> dict[str, Any]:
        with self.db.sessions() as session:
            task_counts = dict(session.execute(
                select(Task.status, func.count()).group_by(Task.status)
            ).all())
            ratings = dict(session.execute(
                select(Feedback.rating, func.count()).group_by(Feedback.rating)
            ).all())
            episode_counts = [
                {"kind": kind, "provider": provider, "status": status, "count": count}
                for kind, provider, status, count in session.execute(
                    select(Episode.kind, Episode.provider, Episode.status, func.count())
                    .group_by(Episode.kind, Episode.provider, Episode.status)
                )
            ]
            return {
                "task_states": task_counts,
                "positive_feedback": ratings.get(1, 0),
                "negative_feedback": ratings.get(-1, 0),
                "episodes": episode_counts,
                "note": "Descriptive counts only. All tool execution is simulated; no RL training.",
            }
