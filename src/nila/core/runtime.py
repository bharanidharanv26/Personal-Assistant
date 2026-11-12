import time
from dataclasses import dataclass

from sqlalchemy import select

from nila.agent.context import ContextBuilder
from nila.agent.service import ChatService
from nila.automation.executor import Executor
from nila.automation.tools import ToolRegistry
from nila.core.config import Settings
from nila.learning.service import LearningService
from nila.llm.base import Provider
from nila.llm.providers import create_provider
from nila.memory.service import MemoryService
from nila.observation.service import ObservationService
from nila.permissions.service import PermissionService
from nila.storage.database import Database, audit
from nila.storage.models import Action, Episode, Task
from nila.tasks.service import TaskService


@dataclass
class Services:
    settings: Settings
    db: Database
    provider: Provider
    memory: MemoryService
    chat: ChatService
    tasks: TaskService
    permissions: PermissionService
    executor: Executor
    observations: ObservationService
    learning: LearningService

    async def close(self) -> None:
        try:
            await self.provider.close()
        finally:
            self.db.close()


def recover_interrupted(db: Database) -> None:
    with db.transaction() as session:
        for task in session.scalars(select(Task).where(Task.status.in_(["planning", "running"]))):
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


def build_services(
    settings: Settings, *, provider: Provider | None = None, tools: ToolRegistry | None = None
) -> Services:
    db = Database(settings.data_dir)
    try:
        db.migrate()
        recover_interrupted(db)
        provider = provider or create_provider(settings)
        tools = tools or ToolRegistry()
        memory = MemoryService(db)
        context = ContextBuilder(db, settings, memory, provider)
        return Services(
            settings=settings, db=db, provider=provider, memory=memory,
            chat=ChatService(db, settings, provider, context),
            tasks=TaskService(db, settings, provider, context, tools),
            permissions=PermissionService(db, settings),
            executor=Executor(db, settings, tools),
            observations=ObservationService(db), learning=LearningService(db),
        )
    except BaseException:
        db.close()
        raise
