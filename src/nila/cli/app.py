import json
import secrets
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

import httpx
import typer
import uvicorn
from filelock import FileLock, Timeout
from pydantic import ValidationError
from rich.console import Console

from nila import __version__
from nila.api.app import create_app
from nila.core.config import Settings
from nila.core.credentials import api_token, store_credential
from nila.storage.database import Database

app = typer.Typer(no_args_is_help=True, help="NILA-AI: personal memory and approved dry-run tasks.")
auth_app = typer.Typer(no_args_is_help=True, help="Manage credentials in the OS credential store.")
db_app = typer.Typer(no_args_is_help=True)
memory_app = typer.Typer(no_args_is_help=True, help="Explicitly save, search, and manage memory.")
task_app = typer.Typer(no_args_is_help=True, help="Plan, inspect, run, and cancel tasks.")
action_app = typer.Typer(
    no_args_is_help=True, help="Inspect and approve individual dry-run actions."
)
consent_app = typer.Typer(no_args_is_help=True, help="Manage manual-observation consent.")
observe_app = typer.Typer(no_args_is_help=True, help="Record manual observations with consent.")
for name, group in (
    ("auth", auth_app), ("db", db_app), ("memory", memory_app), ("task", task_app),
    ("action", action_app), ("consent", consent_app), ("observe", observe_app),
):
    app.add_typer(group, name=name)

console = Console()
errors = Console(stderr=True)


def settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        for error in exc.errors(include_input=False, include_url=False):
            errors.print(f"Configuration error: {error['loc']}: {error['msg']}", markup=False)
        raise typer.Exit(2) from exc


def fail(message: str) -> None:
    errors.print(message, markup=False)
    raise typer.Exit(1)


def resource(value: str) -> str:
    return quote(value, safe="")


def request(
    method: str, path: str, *, payload: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> Any:
    config = settings()
    try:
        token = api_token(config)
        with httpx.Client(
            base_url=config.api_url, headers={"Authorization": f"Bearer {token}"},
            timeout=config.llm_timeout_seconds + config.task_timeout_seconds + 10,
            trust_env=False,
        ) as client:
            response = client.request(method, path, json=payload, params=params)
        if response.is_error:
            try:
                detail = response.json()
            except ValueError:
                detail = {"detail": "Invalid service response"}
            fail(f"Request failed ({response.status_code}): {json.dumps(detail)}")
        return response.json() if response.content else {"status": "ok"}
    except httpx.ConnectError:
        fail("NILA is not reachable. Start `uv run nila serve` in another terminal.")
    except httpx.TimeoutException:
        fail("Request timed out. Inspect the task state before retrying an action.")
    except httpx.HTTPError:
        fail("Local API request failed. Inspect service status before retrying.")
    except RuntimeError as exc:
        fail(str(exc))


def show(data: Any) -> None:
    console.print_json(data=data, ensure_ascii=False)


@app.command()
def version() -> None:
    """Show the installed version."""
    console.print(__version__)


@app.command()
def serve() -> None:
    """Start one local API process on 127.0.0.1."""
    config = settings()
    try:
        api_token(config, create=True)
    except RuntimeError as exc:
        fail(str(exc))
    console.print(f"NILA {__version__} at {config.api_url}; provider={config.llm_provider}")
    console.print("Tools are dry-run only. Press Ctrl+C to stop.")
    uvicorn.run(create_app(config), host="127.0.0.1", port=config.port, access_log=False)


@app.command()
def status() -> None:
    """Check the authenticated service status."""
    show(request("GET", "/health"))


@auth_app.command("init")
def auth_init(rotate: bool = False) -> None:
    """Initialize a local API token; rotating requires restarting the service."""
    config = settings()
    try:
        if rotate:
            if config.api_token is not None:
                fail("NILA_API_TOKEN overrides the credential store; update the environment value.")
            store_credential("api-token", secrets.token_urlsafe(48))
        else:
            api_token(config, create=True)
    except RuntimeError as exc:
        fail(str(exc))
    console.print("Local API credential ready. Restart a running service after rotation.")


@auth_app.command("set-openai-key")
def set_openai_key() -> None:
    """Save a provider key without exposing it in command history."""
    key = typer.prompt("OpenAI API key", hide_input=True).strip()
    if not key:
        fail("API key cannot be empty")
    try:
        store_credential("openai-api-key", key)
    except RuntimeError as exc:
        fail(str(exc))
    console.print("Provider key stored. Configure NILA_LLM_PROVIDER and NILA_OPENAI_MODEL.")


@db_app.command("upgrade")
def db_upgrade() -> None:
    """Apply packaged migrations while the service is stopped."""
    config = settings()
    config.data_dir.mkdir(parents=True, exist_ok=True)
    try:
        with FileLock(config.data_dir / "service.lock", timeout=0):
            database = Database(config.data_dir)
            try:
                database.migrate()
            finally:
                database.close()
    except Timeout:
        fail("Stop the running NILA service before upgrading the database.")
    console.print("Database schema is current.")


@app.command()
def chat(
    message: str,
    conversation: Annotated[str | None, typer.Option(help="Continue a conversation ID")] = None,
) -> None:
    """Send a message with relevant saved memory."""
    show(request("POST", "/chat", payload={"message": message, "conversation_id": conversation}))


@app.command()
def history(conversation_id: str) -> None:
    """Show persisted messages, including failed requests without an assistant reply."""
    show(request("GET", f"/conversations/{resource(conversation_id)}/messages"))


@memory_app.command("add")
def memory_add(content: str, kind: str = "fact", allow_remote: bool = False) -> None:
    """Save a user-supplied fact or preference. Hosted retrieval is opt-in."""
    show(request("POST", "/memories", payload={
        "content": content, "kind": kind, "allow_remote": allow_remote,
    }))


@memory_app.command("list")
def memory_list(limit: int = 100) -> None:
    show(request("GET", "/memories", params={"limit": limit}))


@memory_app.command("search")
def memory_search(query: str, limit: int = 5) -> None:
    show(request("GET", "/memories/search", params={"q": query, "limit": limit}))


@memory_app.command("update")
def memory_update(
    memory_id: str, content: str, kind: str = "fact", allow_remote: bool = False
) -> None:
    """Replace memory content/settings. Remote sharing defaults back to off."""
    show(request("PUT", f"/memories/{resource(memory_id)}", payload={
        "content": content, "kind": kind, "allow_remote": allow_remote,
    }))


@memory_app.command("delete")
def memory_delete(memory_id: str) -> None:
    show(request("DELETE", f"/memories/{resource(memory_id)}"))


@memory_app.command("export")
def memory_export(output: Path | None = None) -> None:
    """Export all memories as JSON, optionally creating a new file."""
    data = request("GET", "/memories/export")
    if output is None:
        show(data)
        return
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
    except OSError as exc:
        fail(f"Export failed: {exc}")
    console.print(f"Memories exported to {output}", markup=False)


@task_app.command("plan")
def task_plan(objective: str) -> None:
    show(request("POST", "/tasks", payload={"objective": objective}))


@task_app.command("list")
def task_list(limit: int = 100) -> None:
    show(request("GET", "/tasks", params={"limit": limit}))


@task_app.command("show")
def task_show(task_id: str) -> None:
    show(request("GET", f"/tasks/{resource(task_id)}"))


@task_app.command("run")
def task_run(task_id: str) -> None:
    """Execute approved remaining dry-run steps, in order."""
    show(request("POST", f"/tasks/{resource(task_id)}/run"))


@task_app.command("cancel")
def task_cancel(task_id: str) -> None:
    show(request("POST", f"/tasks/{resource(task_id)}/cancel"))


@action_app.command("show")
def action_show(action_id: str) -> None:
    show(request("GET", f"/actions/{resource(action_id)}"))


@action_app.command("approve")
def action_approve(action_id: str) -> None:
    """Preview an exact action, then explicitly approve its digest."""
    action = request("GET", f"/actions/{resource(action_id)}")
    show(action)
    typer.confirm("Approve this exact dry-run action?", default=False, abort=True)
    show(request("POST", f"/actions/{resource(action_id)}/approve", payload={
        "digest": action["digest"],
    }))


@action_app.command("deny")
def action_deny(action_id: str) -> None:
    show(request("POST", f"/actions/{resource(action_id)}/deny"))


@action_app.command("revoke")
def action_revoke(action_id: str) -> None:
    show(request("POST", f"/actions/{resource(action_id)}/revoke"))


@action_app.command("execute")
def action_execute(action_id: str) -> None:
    show(request("POST", f"/actions/{resource(action_id)}/execute"))


@consent_app.command("grant")
def consent_grant(lifetime_seconds: int = 3600) -> None:
    """Grant temporary consent for manual observation entries only."""
    show(request("POST", "/consents", payload={
        "scope": "manual_observation", "lifetime_seconds": lifetime_seconds,
    }))


@consent_app.command("list")
def consent_list() -> None:
    show(request("GET", "/consents"))


@consent_app.command("revoke")
def consent_revoke(consent_id: str) -> None:
    show(request("POST", f"/consents/{resource(consent_id)}/revoke"))


@observe_app.command("add")
def observe_add(consent_id: str, content: str) -> None:
    show(request("POST", "/observations", payload={"consent_id": consent_id, "content": content}))


@observe_app.command("list")
def observe_list() -> None:
    show(request("GET", "/observations"))


@observe_app.command("delete")
def observe_delete(observation_id: str) -> None:
    show(request("DELETE", f"/observations/{resource(observation_id)}"))


@app.command()
def feedback(
    target_type: str, target_id: str, rating: Annotated[int, typer.Option(min=-1, max=1)],
    correction: str | None = None,
) -> None:
    """Rate a message, task, or action with --rating 1 or --rating -1."""
    show(request("POST", "/feedback", payload={
        "target_type": target_type, "target_id": target_id,
        "rating": rating, "correction": correction,
    }))


@app.command()
def evaluate() -> None:
    """Show descriptive outcome counts; this does not train a model."""
    show(request("GET", "/evaluation"))


@app.command()
def audit(limit: int = 100) -> None:
    """Inspect metadata-only audit records."""
    show(request("GET", "/audit", params={"limit": limit}))
