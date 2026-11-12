import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any, cast

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from filelock import FileLock, Timeout
from starlette.middleware.trustedhost import TrustedHostMiddleware

from nila import __version__
from nila.automation.tools import ToolRegistry
from nila.core.config import Settings
from nila.core.credentials import api_token
from nila.core.errors import DomainError
from nila.core.runtime import Services, build_services
from nila.core.schemas import (
    ActionView,
    ApprovalRequest,
    ApprovalView,
    ChatRequest,
    ChatResponse,
    ConsentRequest,
    ConsentView,
    FeedbackRequest,
    FeedbackView,
    MemoryCreate,
    MemoryUpdate,
    MemoryView,
    MessageView,
    ObservationRequest,
    ObservationView,
    TaskRequest,
    TaskView,
)
from nila.llm.base import Provider

bearer = HTTPBearer(auto_error=False)


def authenticated(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    expected = cast(str, request.app.state.api_token)
    if credentials is None or not secrets.compare_digest(
        credentials.credentials.encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(401, "A valid local API token is required", headers={
            "WWW-Authenticate": "Bearer"
        })


def services(request: Request) -> Services:
    return cast(Services, request.app.state.services)


ServiceDep = Annotated[Services, Depends(services)]
Limit = Annotated[int, Query(ge=1, le=500)]


def create_app(
    settings: Settings | None = None, *, provider: Provider | None = None,
    tools: ToolRegistry | None = None,
) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        lock = FileLock(settings.data_dir / "service.lock", timeout=0)
        try:
            lock.acquire()
        except Timeout as exc:
            raise RuntimeError("Another NILA service is already using this data directory") from exc
        runtime: Services | None = None
        try:
            application.state.api_token = api_token(settings, create=True)
            runtime = build_services(settings, provider=provider, tools=tools)
            application.state.services = runtime
            yield
        finally:
            try:
                if runtime is not None:
                    await runtime.close()
            finally:
                lock.release()

    app = FastAPI(
        title="NILA-AI", version=__version__, lifespan=lifespan,
        dependencies=[Depends(authenticated)],
        docs_url=None, redoc_url=None, openapi_url=None,
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])

    @app.exception_handler(DomainError)
    async def domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status, content={"detail": exc.detail, "resource_id": exc.resource_id}
        )

    @app.get("/health")
    def health(runtime: ServiceDep) -> dict[str, Any]:
        return {
            "status": "ok", "version": __version__, "provider": runtime.provider.name,
            "remote_provider": runtime.provider.remote, "automation": "dry_run_only",
            "max_steps": runtime.settings.max_steps,
        }

    @app.post("/chat")
    async def chat(request: ChatRequest, runtime: ServiceDep) -> ChatResponse:
        return await runtime.chat.chat(request)

    @app.get("/conversations/{conversation_id}/messages")
    def history(conversation_id: str, runtime: ServiceDep, limit: Limit = 100) -> list[MessageView]:
        return runtime.chat.history(conversation_id, limit)

    @app.post("/memories", status_code=201)
    def create_memory(request: MemoryCreate, runtime: ServiceDep) -> MemoryView:
        return runtime.memory.create(request)

    @app.get("/memories")
    def list_memories(runtime: ServiceDep, limit: Limit = 100) -> list[MemoryView]:
        return runtime.memory.list_memories(limit)

    @app.get("/memories/search")
    def search_memories(
        q: Annotated[str, Query(min_length=1, max_length=4000)], runtime: ServiceDep,
        limit: Annotated[int, Query(ge=1, le=20)] = 5,
    ) -> list[MemoryView]:
        return runtime.memory.search(q, limit)

    @app.get("/memories/export")
    def export_memories(runtime: ServiceDep) -> list[MemoryView]:
        return runtime.memory.list_memories(limit=None)

    @app.put("/memories/{memory_id}")
    def update_memory(memory_id: str, request: MemoryUpdate, runtime: ServiceDep) -> MemoryView:
        return runtime.memory.update(memory_id, request)

    @app.delete("/memories/{memory_id}", status_code=204)
    def delete_memory(memory_id: str, runtime: ServiceDep) -> Response:
        runtime.memory.delete(memory_id)
        return Response(status_code=204)

    @app.post("/tasks", status_code=201)
    async def plan_task(request: TaskRequest, runtime: ServiceDep) -> TaskView:
        return await runtime.tasks.plan(request)

    @app.get("/tasks")
    def list_tasks(runtime: ServiceDep, limit: Limit = 100) -> list[TaskView]:
        return runtime.tasks.list(limit)

    @app.get("/tasks/{task_id}")
    def get_task(task_id: str, runtime: ServiceDep) -> TaskView:
        return runtime.tasks.get(task_id)

    @app.post("/tasks/{task_id}/cancel")
    def cancel_task(task_id: str, runtime: ServiceDep) -> TaskView:
        return runtime.tasks.cancel(task_id)

    @app.post("/tasks/{task_id}/run")
    async def run_task(task_id: str, runtime: ServiceDep) -> TaskView:
        return await runtime.executor.run_task(task_id)

    @app.get("/actions/{action_id}")
    def get_action(action_id: str, runtime: ServiceDep) -> ActionView:
        return runtime.executor.get_action(action_id)

    @app.post("/actions/{action_id}/approve")
    def approve_action(
        action_id: str, request: ApprovalRequest, runtime: ServiceDep
    ) -> ApprovalView:
        return runtime.permissions.approve(action_id, request.digest)

    @app.post("/actions/{action_id}/deny", status_code=204)
    def deny_action(action_id: str, runtime: ServiceDep) -> Response:
        runtime.permissions.refuse(action_id)
        return Response(status_code=204)

    @app.post("/actions/{action_id}/revoke", status_code=204)
    def revoke_action(action_id: str, runtime: ServiceDep) -> Response:
        runtime.permissions.refuse(action_id, revoke=True)
        return Response(status_code=204)

    @app.post("/actions/{action_id}/execute")
    async def execute_action(action_id: str, runtime: ServiceDep) -> ActionView:
        return await runtime.executor.execute(action_id)

    @app.post("/consents", status_code=201)
    def grant_consent(request: ConsentRequest, runtime: ServiceDep) -> ConsentView:
        return runtime.permissions.grant_consent(request)

    @app.get("/consents")
    def list_consents(runtime: ServiceDep, limit: Limit = 100) -> list[ConsentView]:
        return runtime.permissions.list_consents(limit)

    @app.post("/consents/{consent_id}/revoke")
    def revoke_consent(consent_id: str, runtime: ServiceDep) -> ConsentView:
        return runtime.permissions.revoke_consent(consent_id)

    @app.post("/observations", status_code=201)
    def create_observation(request: ObservationRequest, runtime: ServiceDep) -> ObservationView:
        return runtime.observations.create(request)

    @app.get("/observations")
    def list_observations(runtime: ServiceDep, limit: Limit = 100) -> list[ObservationView]:
        return runtime.observations.list(limit)

    @app.delete("/observations/{observation_id}", status_code=204)
    def delete_observation(observation_id: str, runtime: ServiceDep) -> Response:
        runtime.observations.delete(observation_id)
        return Response(status_code=204)

    @app.post("/feedback")
    def feedback(request: FeedbackRequest, runtime: ServiceDep) -> FeedbackView:
        return runtime.learning.feedback(request)

    @app.get("/evaluation")
    def evaluation(runtime: ServiceDep) -> dict[str, Any]:
        return runtime.learning.evaluation()

    @app.get("/audit")
    def audit_events(runtime: ServiceDep, limit: Limit = 100) -> list[dict[str, Any]]:
        return runtime.audits.list(limit)

    return app
