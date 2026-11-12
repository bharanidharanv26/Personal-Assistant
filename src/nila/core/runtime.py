from dataclasses import dataclass

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
from nila.storage.database import Database
from nila.storage.repositories import (
    ApprovalRepository,
    AuditRepository,
    ConsentRepository,
    ConversationRepository,
    ExecutionRepository,
    FeedbackRepository,
    MemoryRepository,
    ObservationRepository,
    TaskRepository,
)
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
    audits: AuditRepository

    async def close(self) -> None:
        try:
            await self.provider.close()
        finally:
            self.db.close()


def build_services(
    settings: Settings, *, provider: Provider | None = None, tools: ToolRegistry | None = None
) -> Services:
    db = Database(settings.data_dir)
    try:
        db.migrate()
        executions = ExecutionRepository(db)
        executions.recover_interrupted()
        provider = provider or create_provider(settings)
        tools = tools or ToolRegistry()
        memories = MemoryRepository(db)
        conversations = ConversationRepository(db)
        tasks = TaskRepository(db)
        approvals = ApprovalRepository(db)
        consents = ConsentRepository(db)
        context = ContextBuilder(settings, memories, conversations, provider)
        return Services(
            settings=settings, db=db, provider=provider,
            memory=MemoryService(memories),
            chat=ChatService(settings, provider, context, conversations),
            tasks=TaskService(settings, provider, context, tools, tasks),
            permissions=PermissionService(settings, approvals, consents),
            executor=Executor(settings, tools, executions, tasks),
            observations=ObservationService(ObservationRepository(db)),
            learning=LearningService(FeedbackRepository(db)),
            audits=AuditRepository(db),
        )
    except BaseException:
        db.close()
        raise
