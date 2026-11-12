# NILA-AI architecture — v0.1

## Decisions

NILA is a single-user modular monolith running natively on Windows. One FastAPI process owns the database and execution lifecycle. The Typer CLI talks to its authenticated loopback API through HTTPX. No Docker, Node runtime, GPU, external database, or task queue is needed.

The initial environment is pinned to Python 3.11 using `uv`. Runtime dependencies and development tools are locked in `uv.lock`. SQLAlchemy manages SQLite access; Alembic owns schema evolution. FTS5 provides local keyword retrieval. A small file lock ensures that recovery runs only when there is no other NILA service using the same database.

## Module boundaries

| Module | Responsibility |
| --- | --- |
| `api` | Authentication, request validation, endpoint contracts |
| `cli` | User commands, credential setup, explicit approval previews |
| `core` | Settings, shared DTOs, errors, service composition and recovery |
| `llm` | Provider protocol, deterministic offline demo, OpenAI adapter |
| `agent` | Bounded prompt construction and conversation coordination |
| `memory` | User-owned facts/preferences, CRUD, export and FTS retrieval |
| `tasks` | Structured planning and persistent task lifecycle |
| `permissions` | Scoped observation consent and action-bound approvals |
| `automation` | Registered tool validation, action digests, execution state machine |
| `observation` | Explicitly submitted notes with active consent |
| `learning` | Feedback and descriptive evaluation, without training |
| `storage` | SQLAlchemy models, transactional helpers, packaged migrations |

Migrations live inside the Python package rather than at the repository root, allowing both editable and wheel installations to migrate their data. Tests cover the module contracts, SQLite integration, and API/CLI workflows.

## Interaction flow

```text
User -> CLI -> authenticated API -> application service
                                   |
                     +-------------+--------------+
                     |                            |
                 context + LLM               SQLite state
                     |
              validated proposal
                     |
           user previews and approves
                     |
        atomic policy/approval transaction
                     |
              registered dry-run tool
                     |
              outcome and feedback
```

There is no autonomous infinite loop. Chat and planning each use one model request with a timeout. Plans have one to five steps by default, with a configurable maximum capped at ten. Output tokens and serialized input characters are bounded. The executor never calls the LLM or requests its own approvals.

The demo provider performs no model reasoning. The hosted adapter uses the OpenAI Responses API, typed plan output, `store=False`, and zero automatic retries. The model ID is explicit configuration. No provider key is needed in demo mode.

## Persistence model

- `memories`: text, fact/preference kind, user provenance, sharing flag, creation/update times.
- `memory_fts`: synchronized full-text index maintained by insert/update/delete triggers.
- `conversations`, `messages`: persisted dialogue with provider and episode linkage.
- `tasks`, `actions`: objectives, structured plans, revisions, action digests and outcomes.
- `approvals`: exact digest, expiration and single-use consumption time.
- `consents`, `observations`: scoped permission records and manual notes.
- `episodes`: chat, plan and action attempts with context references and result metadata.
- `feedback`: one current rating/correction per target; repeated ratings update it.
- `audit_events`: identifier/status metadata, without raw prompts or credentials.

Timestamps are UTC Unix seconds. IDs are random UUID hex strings. SQLite uses foreign keys, WAL, a busy timeout, and short write transactions. `BEGIN IMMEDIATE` serializes policy checks with their state transitions. Model requests and tool execution happen outside database write transactions.

## Memory and context

Saving a memory is an explicit authenticated user action; model responses cannot save one. Updating a memory replaces its content and sharing settings. Keyword retrieval treats query terms as literals, not SQL or FTS syntax.

The prompt contains a system instruction, up to twelve eligible historical messages, and a JSON data envelope with retrieved memory and the current request. Oldest historical messages and lower-ranked memories are removed until the character budget is met. If the request alone exceeds that budget, it is rejected before a model call.

Hosted retrieval only selects memories marked `allow_remote`. Conversation history is provider-specific. Each episode carries memory IDs and update versions, including references inherited from earlier messages. History depending on changed/deleted memory, or on memory no longer shareable with the current provider, is not included in future prompts. This is transitive so a later reply cannot bypass deletion by repeating an earlier reply.

An already-running provider request cannot be retracted by a later deletion. Stored transcripts remain visible for user inspection; memory deletion is not transcript deletion or secure erasure.

## Task execution and recovery

Typical task lifecycle:

```text
planning -> awaiting_approval -> ready -> running -> succeeded
                   |                     |
                cancelled          failed / interrupted
```

Multi-step tasks can return to `ready` or `awaiting_approval` after a step. Approvals default to a five-minute lifetime and can be explicitly renewed if expired and unused. Actions must execute in order. The task deadline is wall-clock time since the first action started, including time spent waiting between subsequent actions.

Before a tool starts, its tool name and arguments are validated again and its exact approval is consumed in the same transaction that marks it running. Captured arguments, rather than a later database read, are passed to the tool. A second concurrent request cannot consume the same approval.

Cancellation stops pending steps. If a step is already running, it may finish and its actual result is recorded; cancellation does not pretend to undo completed work. A timeout records an interrupted outcome. Neither failed nor interrupted actions are automatically retried.

Startup marks unfinished planning, conversation episodes, and running executions interrupted. Unknown outcomes remain inspectable and cannot be replayed. The user can create a fresh plan after review. This is single-use authorization and conservative recovery, not a claim of exactly-once external side effects.

## Learning boundary

Feedback and episodes make future evaluation possible. v0.1 exposes counts by provider, episode kind, status, and rating. These counts measure the current workflow, including simulated actions; they are not model-quality benchmarks or evidence of successful real-world automation.

There is no gradient update, model fine-tuning, reward optimization, or implicit preference extraction. Corrections become personal memory only through an explicit memory command. Future policy experiments require a defined reward, a held-out evaluation set, and a versioned policy with rollback.
