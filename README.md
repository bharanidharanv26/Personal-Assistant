# NILA-AI v0.1

A Windows-native, local-first personal assistant foundation. Includes explicit personal memory, bounded planning, approval-controlled **dry-run** tools, consented manual observations, and feedback records. See `docs/architecture.md` and `docs/permissions.md` for the execution model.

## Quick start (PowerShell)

Run these commands from the NILA-AI directory. Python 3.11 and `uv` are required for the pinned development environment.

```powershell
uv sync --frozen
uv run nila serve
```

The first start stores a random local API token in the operating system credential store, applies database migrations, and listens on `http://127.0.0.1:8765`. Leave that terminal running. Stop it with **Ctrl+C**.

In another terminal in the same project directory:

```powershell
uv run nila status
uv run nila memory add "I prefer jasmine tea" --kind preference
uv run nila chat "What tea do I prefer?"
```

**The default provider is an offline demonstration, not an LLM.** It labels its replies and creates one simulated action per plan. It makes no model API calls. Dependencies must already be installed for offline use.

Manual virtual-environment activation is optional: `uv run` selects `.venv` automatically. In PowerShell, use `.\.venv\Scripts\Activate.ps1`. In Command Prompt, use `.venv\Scripts\activate.bat`.

## Try the complete approval workflow

```powershell
$plan = uv run nila task plan "Draft a tea-break reminder" | ConvertFrom-Json
uv run nila task show $plan.id
uv run nila action approve $($plan.actions[0].id)
# Review the preview and type y to approve this exact action.
uv run nila task run $plan.id
uv run nila feedback task $plan.id --rating 1
uv run nila evaluate
uv run nila audit
```

Every action needs its own approval. Approval lasts five minutes by default. Executing a task requires approval of all remaining steps. Successful execution is **only a simulation**: NILA does not open browsers, modify files, schedule real reminders, or control your computer.

Useful commands:

```powershell
uv run nila --help
uv run nila memory search "tea"
uv run nila memory list
uv run nila memory export
uv run nila memory export --output "$env:LOCALAPPDATA\NILA-AI\exports\memories.json"
uv run nila task list
uv run nila task cancel TASK_ID
uv run nila action deny ACTION_ID
uv run nila action revoke ACTION_ID
uv run nila chat "Continue" --conversation CONVERSATION_ID
uv run nila history CONVERSATION_ID
```

Replace uppercase IDs with IDs returned by earlier commands. File export creates a new file and refuses to overwrite one. Most client commands return JSON that can be piped into `ConvertFrom-Json`.

## Enable hosted LLM reasoning

1. Store your provider key with a hidden prompt:

   ```powershell
   uv run nila auth set-openai-key
   ```

2. Configure the server terminal, choosing a model available to your account that supports the Responses API and structured outputs:

   ```powershell
   $env:NILA_LLM_PROVIDER = "openai"
   $env:NILA_OPENAI_MODEL = "your-model-id"
   uv run nila serve
   ```

   Stop an existing service before restarting it with the new configuration. Alternatively, copy `.env.example` to the ignored `.env` and change the non-secret settings there.

3. If a particular memory may be included in hosted prompts, explicitly opt it in:

   ```powershell
   uv run nila memory add "I prefer concise answers" --kind preference --allow-remote
   ```

Hosted mode sends the current message or task objective, selected same-provider conversation history, and opted-in retrieved memory to the provider. Usage is billed by that provider. Observations and feedback are not automatically sent or used for training. Requests disable provider response storage (`store=False`); provider-specific retention rules still apply.

There is one model call per chat request or planning request, with no automatic retries. Default limits: five plan steps, 16,000 serialized context characters, 1,200 output tokens, and a 30-second model timeout. The context limit is a character budget, not an exact token count. Hosted account-wide spending limits are configured with your provider.

## Consented manual observations

```powershell
$consent = uv run nila consent grant --lifetime-seconds 3600 | ConvertFrom-Json
uv run nila observe add $consent.id "I focused better before lunch today"
uv run nila observe list
uv run nila consent revoke $consent.id
```

Consent applies only to manually submitted notes. No application tracking, screenshots, keyboard monitoring, or background behaviour collection is implemented. Revocation stops new entries; existing entries can be removed with `nila observe delete OBSERVATION_ID`.

## Data, credentials, and configuration

Default Windows data location: **`%LOCALAPPDATA%\NILA-AI\nila.db`**. The service also creates SQLite WAL files and a process lock there. Use `NILA_DATA_DIR` to choose another directory. Only one server process may use a given data directory.

API and provider credentials use the OS credential store. For environments without a supported credential store, set `NILA_API_TOKEN` (at least 32 characters) and, for hosted mode, `NILA_OPENAI_API_KEY`. Credentials set in the environment override stored credentials. `nila auth init --rotate` rotates the stored local token; restart the server afterward.

Personal data in SQLite is **not encrypted by this application**. Audit records contain identifiers and statuses, while the database intentionally stores message, memory, observation, and feedback text. Memory deletion removes the memory record and its search entry; it does not erase previously displayed transcripts or provider-held data. Dependent transcript context is excluded from future prompts after a memory is changed, deleted, or no longer allowed for the current provider.

The API is authenticated, loopback-only through `nila serve`, and has no browser UI. Full configuration options are in [.env.example](.env.example). Run client commands from the same project directory to load the same `.env`.

## Development and checks

```powershell
uv run pytest --basetemp .pytest_tmp -q
uv run ruff check .
uv run mypy
```

Tests use temporary databases and synthetic credentials. LLM calls use test providers or an in-memory HTTP transport; they do not use a real key or contact a hosted model.

Migrations run automatically at server startup. To run them explicitly while the server is stopped:

```powershell
uv run nila db upgrade
```

Migrations are packaged under `src/nila/storage/migrations/` so an installed CLI can find them outside this checkout. A startup lock prevents another server from treating an active execution as interrupted. Stop NILA before making a database backup; copy the database only after clean shutdown so WAL transactions have been checkpointed.

## v0.1 boundaries

- Explicit memory, conversation history, structured plans, task state, and feedback persist across restarts.
- Approval, denial, revocation, expiry, cancellation, execution ordering, and interrupted-run recovery are enforced in application code.
- Feedback updates descriptive evaluation counts. It does not update model weights or automatically create memories.
- Tool execution is dry-run only. Browser/desktop adapters, semantic embeddings, background observation, scheduling, and reinforcement-learning optimization are later milestones.

Architecture: [docs/architecture.md](docs/architecture.md) · Permissions: [docs/permissions.md](docs/permissions.md) · API: [docs/api.md](docs/api.md) · Roadmap: [docs/roadmap.md](docs/roadmap.md)
