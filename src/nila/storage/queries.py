from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from nila.core.errors import DomainError
from nila.core.schemas import ActionView, TaskView
from nila.storage.models import Action, Base, Task

T = TypeVar("T", bound=Base)


def require(session: Session, model: type[T], record_id: str) -> T:
    value = session.get(model, record_id)
    if value is None:
        raise DomainError(404, f"{model.__name__} not found", record_id)
    return value


def task_view(session: Session, task: Task) -> TaskView:
    view = TaskView.model_validate(task)
    view.actions = [
        ActionView.model_validate(action)
        for action in session.scalars(
            select(Action).where(Action.task_id == task.id).order_by(Action.position)
        )
    ]
    return view


TERMINAL_TASK_STATES = {"succeeded", "failed", "cancelled", "interrupted"}
