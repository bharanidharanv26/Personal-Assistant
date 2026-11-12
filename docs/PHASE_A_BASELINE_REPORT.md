# NILA AI - Phase A Baseline and Supabase Migration Readiness Report

**Inspection date:** 2026-11-12  
**Project:** `C:\Users\bhara\Documents\NILA-AI`  
**Phase:** Inspection, existing-test execution, and documentation only  
**Decision:** Preserve the existing implementation and proceed incrementally after approval. The current SQLite foundation passes its existing tests; it is not yet a verified Supabase implementation.

## 1. Executive summary

Nila AI is an existing Python 3.11/FastAPI modular application with a working CLI, SQLAlchemy persistence, explicit memory, bounded planning, approval-controlled dry-run execution, consented manual observations, feedback, and evaluation counts.

The current database is **SQLite**, not a separately managed PostgreSQL server. Supabase PostgreSQL will be a new persistence target. There is no React application, Supabase client, PostgreSQL driver configuration, pgvector integration, or real desktop automation in the inspected application.

The baseline test command completed with:

```text
35 passed, 1 warning in 29.66s
PytestExitCode : 0
```

No test failed, errored, or was skipped. The warning is a dependency deprecation notice, explained in section 4. Passing this suite establishes the existing SQLite/dry-run baseline; it does not prove PostgreSQL concurrency, RLS, live hosted-model access, or actual desktop execution.

The most important migration work is preserving atomic approval consumption, adding owner-based isolation, replacing machine-local recovery assumptions, converting data types without losing provenance, and distinguishing cloud persistence from permission to send content to AI providers.

### Phase A boundaries observed

- Application source, tests, dependency declarations, lockfile, environment configuration, and existing migrations were not edited.
- No package installation, dependency synchronization, Git commit/reset, Supabase connection, frontend development, or production database migration was performed.
- No environment file or user/shell environment setting was changed. Existing tests retained their own isolated process fixtures and synthetic child-process configuration.
- No real API key, password, or token was requested or printed. The operating-system credential store was not queried.
- The existing tests necessarily provisioned schemas in **new disposable SQLite test databases only**, under a fresh temporary directory outside the project. No application/cloud database tables were created or changed.
- Existing project test databases were left untouched. This report is the only intentionally authored project file in Phase A; its destination did not exist before creation.

## 2. Inspection scope and repository status

Inspected the application modules, all eight test modules and their fixtures, dependency manifest and lockfile metadata, configuration template, database models and migration code, current documentation, Git state, relevant environment-variable presence, and database/credential-file names. Generated dependency/build/cache directories were inventoried rather than treated as application source.

The previous inspection report was used as context; findings here were checked against the current checkout.

| Item | Observed status |
| --- | --- |
| Git repository root | `C:/Users/bhara/Documents/NILA-AI` |
| Branch | `main` |
| Commits | One initial commit, `9715fc5` (`Initial commit - Nila AI`), on `main`; up to date with `origin/main` |
| Initial non-ignored project files | 57, all tracked in that commit |
| Source files | 38 Python files, including package initializers and migration files |
| Tests | Eight test modules plus `tests/conftest.py` |
| Existing documentation | `README.md`, `docs/architecture.md`, `docs/api.md`, `docs/permissions.md`, `docs/roadmap.md` |
| Report destination | `docs/PHASE_A_BASELINE_REPORT.md` was absent |
| Applicable `AGENTS.md` | None found in the project or checked ancestor locations |
| Existing local environment | `.venv/`, managed through `uv` |
| Python used for this test run | 3.11.9, from `.venv/Scripts/python.exe` |
| Python project pin | `.python-version` specifies `3.11` |
| Declared Python range | `>=3.11,<3.15`; this review verifies only the installed 3.11 interpreter |
| Frontend manifests | No `package.json`, Vite configuration, or TypeScript project found |
| Editor tooling | `.qodo/agents/` and `.qodo/workflows/` exist and were empty when inspected |

### Preservation evidence

The working tree is backed by the initial commit, so Git can verify the baseline directly. After this report was created, `git status --porcelain=v1 --untracked-files=all` listed only `?? docs/PHASE_A_BASELINE_REPORT.md`, and both `git diff --quiet` (working tree versus index) and `git diff --cached --quiet` (index versus `HEAD`) exited `0`. The 57 tracked files were also re-hashed after report creation by enumerating `git ls-files`; their aggregate SHA-256 was:

```text
7a77eace667d500e47343f954273413408968a5b9a1e5bf238b6c050a970a935
```

This is the same aggregate recorded before and after the baseline test run. The aggregate is computed over newline-joined `relative-path:SHA256` entries, using ordinal path ordering and uppercase per-file SHA-256 hex. The report itself is excluded from that inventory. This verifies the tracked source/configuration/documentation bytes against the pre-test snapshot, not ignored runtime artifacts or external files.

**Repository risk:** the initial commit is the only restore point, and the working tree already adds this uncommitted report. Before an approved refactor, create a reviewed checkpoint commit and preserve any actual application database. A Git commit should only be made on explicit instruction.

## 3. Current architecture and implemented functionality

```text
Typer/Rich CLI
    |
    | HTTPX + local bearer authentication
    v
FastAPI on 127.0.0.1
    |
    +-- Chat/context -> demo or OpenAI provider
    +-- Explicit memory -> SQLite FTS5 retrieval
    +-- Task planning -> validated dry-run proposals
    +-- Permissions -> approval / consent state
    +-- Executor -> simulated tool result
    +-- Observations / feedback / evaluation
    |
    v
SQLAlchemy sessions -> SQLite + Alembic
```

### Source inventory

All paths below are relative to the project root. Every listed package directory also contains its existing `__init__.py`; the top-level `src/nila/__init__.py` declares version `0.1.0`.

| Location | Existing files and responsibility |
| --- | --- |
| `src/nila/api/` | `app.py`: authenticated endpoints, dependency wiring, startup/shutdown, local process lock |
| `src/nila/cli/` | `app.py`: service startup, local credentials, database upgrade, chat/history, memory, task/action, consent/observation, feedback/evaluation/audit commands |
| `src/nila/core/` | `config.py`, `credentials.py`, `errors.py`, `runtime.py`, `schemas.py`: settings, secrets access, domain errors, service composition/recovery, Pydantic contracts |
| `src/nila/llm/` | `base.py`, `providers.py`: provider protocol, prompt structure, offline demo and OpenAI adapters |
| `src/nila/agent/` | `context.py`, `service.py`: memory/history selection, context bounds, conversation turns |
| `src/nila/memory/` | `service.py`: explicit memory CRUD, export selection, literal keyword search |
| `src/nila/tasks/` | `service.py`: planning, inspection, listing, cancellation |
| `src/nila/permissions/` | `service.py`: approval/denial/revocation, expiry handling, observation consent |
| `src/nila/automation/` | `tools.py`, `executor.py`: action digests, tool validation, transactional claims and completion |
| `src/nila/observation/` | `service.py`: manual notes with active scoped consent |
| `src/nila/learning/` | `service.py`: validated feedback targets, feedback replacement, descriptive counts |
| `src/nila/storage/` | `database.py`, `models.py`, `queries.py`: SQLite engine, ORM schema, query/view helpers |
| `src/nila/storage/migrations/` | `env.py`, `versions/0001_foundation.py`, and package initializers: programmatically invoked Alembic history |

Important root configuration consists of `pyproject.toml`, `uv.lock`, `.python-version`, `.env.example`, and `.gitignore`. The lockfile records an editable `nila-ai` 0.1.0 package. Existing `dist/` packages and caches are generated artifacts, not a replacement for the source.

### Dependencies

Runtime declarations: Alembic, FastAPI, Filelock, HTTPX, Keyring, OpenAI, Platformdirs, Pydantic, Pydantic Settings, Rich, SQLAlchemy, Typer, Uvicorn. Development declarations: Mypy, Pytest, Pytest Asyncio, Ruff. Hatchling is the build backend.

Installed versions confirmed by the successful diagnostic and test runner:

| Component | Version |
| --- | --- |
| Python | 3.11.9 |
| FastAPI | 0.162.5 |
| SQLAlchemy | 2.1.8 |
| Starlette | 1.10.0 |
| HTTPX | 0.28.1 |
| Pytest | 9.2.0 |
| Pytest Asyncio | 1.4.1.post1 |
| Pluggy | 1.7.0 |

### Features supported by this baseline

| Capability | Evidence and boundary |
| --- | --- |
| Local API and installed CLI | Live loopback-server acceptance test passed, including authentication and the CLI workflow |
| Memory CRUD and lexical retrieval | Create/search/update/delete, Tamil text, punctuation handling and FTS synchronization tests passed |
| Conversation persistence | API workflow verifies stored dialogue behavior and restart persistence; context tests verify sharing controls and transitive memory provenance |
| Bounded planning | Structured demo plans work; step-budget failures are tested |
| Approval enforcement | Tests cover missing, expired, altered, denied, revoked, cancelled and replayed authorization |
| Duplicate prevention | Two concurrent coroutines in one runtime consume an approval once; cross-process/PostgreSQL behavior remains untested |
| Interrupted execution | Recovery, tool failure, tool timeout and cancellation between steps are tested |
| Manual observation consent | Revoked, expired and wrong-scope consent are rejected |
| Feedback | Repeated ratings replace prior feedback; feedback does not silently create personal memory |
| OpenAI adapter | Request shape, output budgets, structured parsing and no rate-limit retry are verified with mocked HTTP responses |
| Explicit exports | Export commands exist; export-file overwrite/round-trip behavior lacks dedicated baseline coverage |

The demo provider is deterministic and does not reason using an AI model. All registered tools are dry-run simulations. No local inference model, background monitoring, browser/terminal/file automation, training loop, React dashboard, Supabase Auth/Storage/Realtime, or semantic embedding retrieval is implemented.

## 4. Exact baseline test execution and results

### Command

Working directory: `C:\Users\bhara\Documents\NILA-AI`.

```powershell
& '.\.venv\Scripts\python.exe' -B -m pytest -p no:cacheprovider --basetemp 'C:\Users\bhara\AppData\Local\Temp\opencode\nila-phase-a-20261112-7f18b6d9' -ra
```

Before execution, the temporary parent was verified to exist and the chosen test destination was verified to be absent. This matters because pytest can clear an existing `--basetemp` directory. The project's existing `.pytest_tmp/` was not reused.

- Direct invocation of the installed interpreter avoided `uv sync`, dependency installation, or lockfile changes.
- `-B` disabled bytecode writing in the pytest interpreter.
- `-p no:cacheprovider` prevented pytest from updating its normal project cache.
- The suite's existing temporary database fixtures, fake credentials and mock providers were used without modification.
- The acceptance test started and terminated its own temporary loopback API server. The ordinary user service was not started.

### Captured result

```text
platform win32 -- Python 3.11.9, pytest-9.2.0, pluggy-1.7.0
rootdir: C:\Users\bhara\Documents\NILA-AI
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.16.0, platformdirs-4.14.5, asyncio-1.4.1.post1
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
collected 35 items

tests\acceptance\test_live_cli.py .                                      [  2%]
tests\integration\test_api_workflow.py ....                              [ 14%]
tests\integration\test_failures.py .....                                 [ 28%]
tests\integration\test_openai_adapter.py ..                              [ 34%]
tests\integration\test_permissions.py ..............                     [ 74%]
tests\integration\test_storage.py ...                                    [ 82%]
tests\unit\test_cli.py ..                                                [ 88%]
tests\unit\test_context.py ....                                          [100%]

35 passed, 1 warning in 29.66s
PytestExitCode : 0
```

| Test module | Passed | Main coverage |
| --- | ---: | --- |
| `tests/acceptance/test_live_cli.py` | 1 | Installed CLI against a real temporary local API |
| `tests/integration/test_api_workflow.py` | 4 | End-to-end workflow, restart, authentication, input validation, feedback |
| `tests/integration/test_failures.py` | 5 | Provider failure, plan limit, tool failure, cancellation, timeout |
| `tests/integration/test_openai_adapter.py` | 2 | Mocked hosted requests, structured output, rate-limit handling |
| `tests/integration/test_permissions.py` | 14 | Approval integrity/lifecycle, concurrency, recovery, consent; includes parametrized cases |
| `tests/integration/test_storage.py` | 3 | Repeated migrations, ORM/schema agreement, FTS, process lock |
| `tests/unit/test_cli.py` | 2 | Help/version and explicit approval confirmation |
| `tests/unit/test_context.py` | 4 | Cloud-sharing filters, transitive deletion, revoked sharing, context size |
| **Total** | **35** | **0 failed, 0 errors, 0 skipped** |

### Warning investigation

The warning appeared at `.venv/Lib/site-packages/fastapi/testclient.py:1`:

```text
StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
```

Inspection of installed `starlette/testclient.py`, lines 25-44, confirms that it first attempts to import `httpx2`, falls back to `httpx`, and emits this warning. The fallback worked for all existing tests. This is a development dependency compatibility issue, not a failed application assertion. No package was installed and the warning was not suppressed.

**Recommendation:** during an approved dependency-maintenance step, evaluate the supported TestClient dependency combination and rerun API/CLI tests. Do not automatically replace the application's HTTPX client, which is also used by the CLI and mocked OpenAI tests. Likely files: `pyproject.toml`, `uv.lock`, and test imports/fixtures only if required.

### Auxiliary diagnostic issue

A separate broad package-version enumeration command exceeded the shell's 120,000 ms timeout without output. A smaller unbuffered query then completed and reported the installed versions above. The timeout's root cause was not established; it is not counted as a pytest failure. The full test suite was run once for this baseline, with no application fixes or test suppression.

Lint, type checking, packaging, live hosted LLM access, and Supabase integration were not newly verified in Phase A. Earlier results are not presented as new executions here.

## 5. Database, migration and secret-file status

### Current database path

`core/config.py` uses `platformdirs.user_data_path("NILA-AI", appauthor=False)` unless overridden through settings. The resolved default path on this machine was confirmed as:

```text
C:\Users\bhara\AppData\Local\NILA-AI\nila.db
```

At inspection time:

- The default data directory and database file did not exist.
- No project `.env` existed.
- `NILA_DATA_DIR` was absent from the inspection process environment.
- The project contains older disposable SQLite databases at `.pytest_tmp/<test-name>/data/nila.db` and a Mypy cache database at `.mypy_cache/3.11/cache.db`. These are not the configured application database and were not migrated, moved, opened for content inspection, or deleted.
- This baseline produced new disposable databases only below the temporary path in section 4.

No claim is made that a database cannot exist in an unrelated directory or under another shell's settings. Confirm the actual source location again before any future import. Do not use a filename match to decide that a test database contains the user's real data.

### Alembic history

There is one application revision:

```text
<base> -> 0001_foundation (head)
down_revision = None
```

Location: `src/nila/storage/migrations/versions/0001_foundation.py`.

`storage/database.py` creates an Alembic `Config` programmatically, supplies an existing connection, and upgrades to `head`. `migrations/env.py` requires that supplied connection. There is no root `alembic.ini`; this is intentional, not evidence of missing migration support.

The revision creates 11 application tables, a `memory_fts` virtual table, and three FTS synchronization triggers. Alembic also maintains its own version bookkeeping. Fresh/repeated migration and ORM metadata consistency tests passed against temporary databases. No actual user database existed at the configured location, so there was no deployed user-database revision to verify.

The ordinary service currently migrates automatically in `build_services()`. That startup behavior must change before using restricted production database credentials.

### Existing ORM schema

| Model | Table | Important relationships/constraints |
| --- | --- | --- |
| `Memory` | `memories` | Content, fact/preference kind, source, sharing flag, timestamps |
| `Conversation` | `conversations` | Conversation identity and creation time |
| `Episode` | `episodes` | Chat/plan/action attempt, generic resource reference, memory-version references, outcome |
| `Message` | `messages` | FKs to conversation and episode; conversation/time index |
| `Task` | `tasks` | Objective, title, provider, revision, lifecycle and start time |
| `Action` | `actions` | Task FK; unique `(task_id, position)`; typed arguments at the application boundary, digest and result |
| `Approval` | `approvals` | Unique action FK; digest, expiry, consumption time |
| `Consent` | `consents` | Scope, expiry, revocation time |
| `Observation` | `observations` | Consent FK and explicit note content |
| `Feedback` | `feedback` | Unique `(target_type, target_id)`; target existence is checked in Python, not by a target FK |
| `AuditEvent` | `audit_events` | Generic resource reference and metadata-only event details |

Primary keys are 32-character UUID hex strings stored in string columns. Timestamps are floating-point Unix seconds. Structured fields use SQLAlchemy `JSON`. There are no user-ownership fields, RLS policies, vector columns, or repository classes. `storage/queries.py` supplies query helpers, while domain services and the audit API route still issue ORM queries directly.

### Secret handling findings

- `.env.example` contains configuration placeholders and non-secret defaults.
- `.gitignore` excludes `.env`, `.env.*` other than the example, databases, logs, virtual environments, caches, exports and builds.
- Filename-based checks, including ignored project paths outside dependencies/test artifacts, found no project environment/credential/key files requiring inspection. A `credentials` filename match was generated Python bytecode for the credential-loader module, not a credential file.
- Presence-only checks for the existing NILA data/API/model settings and common database/Supabase/LLM secret settings returned absent for the checked names. No values were printed. This was not a machine-wide secret scan.
- Current code can read real credentials from the OS credential store. That store was deliberately not queried, so absent environment variables do not imply there are no stored credentials.
- Model credentials currently allow an environment setting and a Keyring fallback. A future environment-only model-credential policy requires a documented compatibility change, not deletion of stored keys.

### Recommended backup procedure if a real database is found

This is a recommendation only; no backup or database mutation was performed.

1. Confirm the exact configured source and obtain a reviewed source checkpoint. Keep backups outside the repository and outside any destination that might overwrite the source.
2. For this small single-user application, stop its service cleanly before cutover. If it must remain running, use SQLite's supported online backup API to a new destination rather than copying the active file.
3. Prefer a SQLite backup snapshot that includes committed WAL data. Copying only `nila.db` while WAL transactions are outstanding can omit committed changes. Never delete `-wal` or `-shm` files to force a clean-looking source.
4. Use a unique, non-existing backup filename and retain the original database. Restrict access to the backup because it contains personal text.
5. Validate a backup/restored copy with `PRAGMA integrity_check`, `PRAGMA foreign_key_check`, table counts, representative relationships and application read tests. These checks and any restore should target a copy, not overwrite the source.
6. Preserve the source and verified backup until PostgreSQL import reconciliation and rollback decisions are complete. The existing memory JSON export is not a full database backup: it omits conversations, tasks, approvals and other history.

## 6. Transaction boundaries and execution guarantees

### How SQLite writes are serialized today

`Database.transaction()` opens a fresh SQLAlchemy session and executes `BEGIN IMMEDIATE`. SQLite permits one writer at a time, so this obtains the write reservation before policy reads and updates. The context manager commits on success and rolls back on exceptions. Connections enable foreign keys, WAL, and a 5,000 ms busy timeout.

Read-only methods use separate ordinary sessions. The lock file prevents a second API process using the same local data directory, while the database write transaction protects individual write operations.

### Existing transaction boundaries

| Operation | Atomic database unit | Work outside that unit |
| --- | --- | --- |
| Memory create/update/delete | Memory change, trigger-maintained FTS update and audit insertion | Subsequent retrieval/context generation |
| Chat | Conversation creation/lookup; then a separate user-message/episode transaction; then a response/episode-outcome/audit transaction | Context assembly and model call; no write lock held during reasoning |
| Planning | Initial task/episode transaction; later plan/actions/task-state/outcome/audit transaction | Structured model request and validation |
| Approval/denial/revocation | State checks, approval mutation, related task/action changes and audit | User preview and CLI confirmation occur before approval submission |
| Consent/observation | Consent change plus audit, or active-consent check and observation insert plus audit | User decisions and manual entry |
| Execution claim | Task/action/approval/order/digest checks, approval consumption, running state, episode and audit | Tool execution starts after commit |
| Execution completion | Action result, task state, episode outcome and audit | The tool may already have produced an external effect in future adapters |
| Cancellation | Terminal-state check and cancellation of pending actions plus audit | An already-running step may finish |
| Feedback | Target validation, feedback insert/update and audit | No model training or automatic memory creation |
| Startup recovery | Global scan and marking of unfinished tasks/actions/episodes | Currently assumes exclusive ownership of this local database |

### Exact-action approval contract

`automation/tools.py` hashes a canonical JSON payload containing task ID, task revision, action position, tool name/version and arguments. `permissions/service.py` verifies that the reviewed digest still describes the stored action.

`automation/executor.py` then checks task state, previous steps, approval availability/expiry, current digest and task deadline inside the serialized write transaction. It consumes the approval before the tool starts and records a running episode/audit event in that same commit. The approved arguments are captured and passed to the tool rather than re-read later.

The implementation therefore provides single-use authorization under its current SQLite assumptions. It does **not** provide a general exactly-once guarantee for an external effect and a remote database commit together. A crash after a future real tool succeeds but before result persistence will require an unknown/interrupted outcome and review, not automatic replay.

### PostgreSQL translation required

`BEGIN IMMEDIATE` has no PostgreSQL equivalent with the same database-wide behavior. Ordinary read-then-write ORM code at PostgreSQL's common `READ COMMITTED` isolation level can allow two workers to observe the same unused approval.

The future claim operation should lock the parent task and relevant action/approval rows in a fixed order, check ownership and database time after obtaining the locks, and use a conditional update that can consume an unused matching approval only once. The action state, attempt/claim identifier and audit event must commit together. Cancellation and approval writers must participate in the same locking protocol.

Claims should have stable identifiers so a lost network acknowledgement can be reconciled by reading durable state. Do not blindly retry a tool or assume a timed-out database call rolled back. No database write transaction should remain open during an LLM call or tool execution.

## 7. Supabase readiness and target responsibilities

**Assessment:** the module boundaries and existing behavioral tests are a useful starting point. Persistence is not a drop-in PostgreSQL swap because SQLite SQL, writer locking, automatic migrations, local recovery, primitive types and global ownership assumptions are embedded in the current code.

Recommended future data path:

```text
React dashboard / existing CLI
              |
              v
FastAPI: identity, permissions, planning and application services
              |
       concrete repositories
              |
 SQLAlchemy + PostgreSQL driver
              |
      Supabase PostgreSQL

Dedicated Supabase SDK boundary -> Auth / Storage / Realtime when needed

Approved execution commands -> Windows Python desktop agent
Selected experience datasets -> separate Python training/evaluation component
```

SQLAlchemy can connect to Supabase-managed PostgreSQL without installing a separate PostgreSQL server. Retaining it preserves useful transaction patterns. The SDK handles Supabase service APIs; independent SDK HTTP writes cannot be treated as part of an ORM transaction.

Supabase stores durable application state, vectors, files and relevant events. Long-running reasoning, local browser/terminal/application operations, and RL training remain Python workloads outside the database platform.

For later Storage, use private buckets, ownership-linked metadata and scoped/signed access rather than public personal-document URLs. Realtime events should notify a UI to refresh authorized state, not authorize or directly trigger tool execution. Duplicate or reordered notifications must not cause duplicate actions.

## 8. Security, technical and data-loss risks

These distinguish current limitations from migration blockers; they are not claims that the present single-user dry-run application has already suffered a breach or lost data.

| Risk | Evidence / consequence | Priority and recommendation |
| --- | --- | --- |
| Limited restore history | One initial commit (`9715fc5`) exists; no later checkpoint protects the approved baseline/report | Before refactor: preserve a reviewed checkpoint; do not overwrite existing work |
| Missing owner isolation | Models and `require()` perform global ID lookups; no users/ownership/RLS | Required before shared cloud persistence: owner-aware queries, relational constraints and tested RLS |
| Single local bearer identity | Current token authenticates the local app, not distinct users/devices | Preserve for local-only operation; introduce verified identity/device authorization before remote or multi-device access |
| SQLite-only serialization | `BEGIN IMMEDIATE` currently prevents read/check/update races | Required before PostgreSQL execution: row locking and single-use conditional claims |
| Local recovery assumption | Filelock is machine-local; startup marks all running/planning rows interrupted | Required before shared workers: ownership, lease expiry and fencing; one worker must not recover another active worker's job |
| In-memory conversation lock | `_busy_conversations` exists only in one Python process | Add database-backed operation ownership before multiple API processes can work on one conversation |
| Automatic migration at startup | `build_services()` runs schema upgrades | Use deployment-only migration credentials; runtime performs schema checks without DDL privileges |
| Partial/uncertain remote writes | Claim, external effect and completion occur across separate commits | Stable attempt identifiers, reconciliation, explicit unknown outcomes and no blind side-effect retries |
| Blocking ORM work in async flows | Async chat/planning/execution use synchronous sessions directly | Offload complete synchronous units to worker threads or deliberately adopt async database access; never share a session across concurrent workers |
| Unchecked polymorphic references | Feedback/episode/audit resource IDs are partly application-validated | Add actual FKs/checks where possible; preserve intentional historical references without accidental cascade loss |
| Mutable audit records | Audit is metadata-only but has no database append-only enforcement | Narrow grants, append-only event writes and explicit retention procedures; do not label it tamper-proof |
| Clock and version precision | `time.time()` controls deadlines and exact floating-point memory versions | Database-authoritative lease/approval time; integer content revisions; tested timestamp conversion |
| Cloud sharing ambiguity | `allow_remote` currently controls model context, not database residency | Separate persistence consent, cloud-LLM sharing and cloud-embedding sharing before import |
| Context disclosure race | A selected/in-flight provider request cannot be retracted by a later revocation | Define revocation timing and revalidate outbound context before sending where feasible; never promise retroactive deletion |
| Plaintext personal data | SQLite contains messages, notes, memory and feedback; export files duplicate some data | Restrict backups/exports and define cloud retention/deletion; logical deletion is not guaranteed physical erasure |
| FTS behavior changes | Literal OR terms and SQLite BM25 differ from PostgreSQL text search | Preserve useful Unicode behavior and document deliberate ranking/stop-word changes |
| Environment alias mismatch | Current loader prefixes settings with `NILA_` | Explicitly support future `SUPABASE_*`, `DATABASE_URL`, `LLM_API_KEY` names; do not silently ignore required configuration |
| Test-client deprecation | Current Starlette uses its HTTPX fallback | Non-blocking today; handle in an approved dependency maintenance change |

### Specific data-loss hazards during migration

- Copying an active SQLite database without its committed WAL state.
- Replacing the old Alembic revision or applying its SQLite-only DDL to PostgreSQL.
- Regenerating UUIDs instead of preserving identity and dependent references.
- Changing UUID serialization and invalidating signed-off action digests without retaining the historical payload/version.
- Rounding timestamps and accidentally treating outdated memory references as current.
- Conflating SQL NULL with JSON null or changing nested payload types during JSONB conversion.
- Cascading deletions through conversations, approvals, episodes or audit history without an explicit retention design.
- Importing earlier test fixtures as personal data, or running integration cleanup against a real Supabase project.
- Allowing writes to both old and new databases during an uncontrolled cutover, producing divergent histories.
- Automatically uploading existing private records just because a Supabase connection is configured.

The migration should retain its source, produce an import/reconciliation manifest, preserve identifiers, verify counts and relationships, and switch the authoritative write target only after verification. A rollback after new PostgreSQL writes needs an explicit reconciliation plan; simply switching back to an older SQLite copy would lose those newer writes.

## 9. Proposed target tables and reuse decisions

These are design recommendations, not created tables. Initial PostgreSQL work should preserve current features before adding future learning/product concepts.

| Proposed table | Existing mapping | Recommendation and verification |
| --- | --- | --- |
| `users` | None | Add for owner identity in the database milestone. An optional unique `auth_user_id` can link to Supabase Auth later. Test missing/wrong-owner access. |
| `conversations` | `Conversation` | Reuse behavior; add owner FK and timezone-aware timestamps. Test dialogue persistence and isolation. |
| `messages` | `Message` | Reuse conversation/episode links and provider data; enforce same-owner parent links. Test ordering, history isolation and import fidelity. |
| `user_preferences` | Personal preferences currently live in `Memory.kind = preference` | Defer separate structured settings until required. Do not introduce competing sources of truth. Test mapping/precedence when introduced. |
| `memories` | `Memory` | Reuse and extend with owner, category, confidence, access/expiry, revisions and explicit sharing/lifecycle status. Test correction/deletion/provenance. |
| `projects` | None | Defer until grouping tasks is exposed. Test task ownership and project relationships then. |
| `tasks` | `Task` | Reuse lifecycle/revision; add ownership and later priority/project fields. Test preserved API behavior and terminal transitions. |
| `task_steps` | Current ordered `Action` rows act as steps | Defer separation until planned steps need independent state or multiple attempts/actions. Test sequence and migration of existing positions when introduced. |
| `observations` | `Observation` | Retain consent linkage; add ownership and future source/retention metadata. Test active consent and user isolation. |
| `feedback` | `Feedback` | Reuse ratings/corrections. Prefer explicit nullable message/task/action FKs with exactly-one-target checks and per-owner uniqueness. Test invalid/cross-owner targets and replacement semantics. |
| `consents` | `Consent` | Preserve as a first-class table; add owner and appropriate timestamps. Test revocation/expiry concurrent with collection. |
| `action_approvals` | `Approval` / `approvals` | Reuse authorization contract; optionally map to the requested name without renaming Python classes/API routes. Record approver, digest/version, expiry and consumption. Test concurrent consume/renew/revoke. |
| `agent_actions` | `Action` / `actions` | Reuse proposal/result fields; add owner, device/worker identity and claim/attempt metadata when needed. Test stale-worker completion and no replay. |
| `execution_logs` | Partly overlaps `AuditEvent` and action `Episode` records | Keep the existing general audit stream initially. Introduce a separate per-attempt execution-log table only if its structure/retention is needed; do not lose memory/consent audit events by blindly renaming them. Test transactional log writes and restricted mutation. |
| `rl_experiences` | `Episode` plus linked feedback provide source records | Defer until a defined experience schema is used: state, action, reward, next state, termination/truncation, outcome and policy version. Episodes are not automatically training examples. Test dataset provenance and completeness. |
| `learning_metrics` | Counts are currently computed by `LearningService.evaluation()` | Defer persistence until versioned evaluation runs exist. Test metric reproducibility against fixed datasets/policies. |

Additional existing/supporting concepts must be preserved:

- **`episodes`:** keep conversation/planning/execution records and their context provenance; messages already reference them.
- **`audit_events`:** retain general audit events, including non-execution events. A separate execution-log table must not replace this history accidentally.
- **`memory_embeddings`:** introduce in the semantic-memory phase, separately from ordinary memory text.
- **Execution ownership/leases:** a small supporting schema is justified when the persistent database becomes shared. Define it together with claim/recovery tests, not as a generic job framework.

### PostgreSQL field and constraint changes

| Current representation | Recommended target | Why / how to verify |
| --- | --- | --- |
| UUID hex string columns | Native UUID, retaining each existing UUID value | Smaller, validated identifiers; round-trip existing references and legacy API serialization |
| Float Unix timestamps | `TIMESTAMPTZ`, with explicit UTC application serialization | Represent timezone-aware instants; test conversion precision, ordering and expiry boundaries |
| Float-valued memory references | Integer `content_revision` and explicitly mapped old references | Prevent equality/rounding errors from reintroducing stale memory into context |
| SQLAlchemy `JSON` | PostgreSQL `JSONB` where structured querying is useful | Preserve payload values and SQL NULL/JSON-null semantics; index only demonstrated query paths |
| String status/role/kind fields | Documented values plus database CHECK constraints | Reject invalid out-of-band state; compare with application enums/validation |
| Global resource IDs | Owner columns, owner-aware indexes and ownership-consistent FKs | Prevent a child row from referencing another owner's parent |
| FTS5 virtual table/triggers | PostgreSQL text-search vector and GIN index | Support lexical retrieval using parameters; verify Unicode/Tamil, punctuation, deletion and ranking expectations |
| Basic lookup indexes | Owner-leading indexes, conversation/time, task/position, action/approval and status/lease lookups | Match actual filters and constraint needs; inspect query plans with representative data |

Use check constraints such as confidence in `[0, 1]`, valid feedback ratings, positive step positions and coherent expiry times. Use partial indexes only with suitable stable predicates; do not put a moving `now()` condition into an index predicate. Keep arbitrary audit resource references intentionally generic where a strict FK would prevent required historical retention, and document that choice.

## 10. Memory and semantic retrieval readiness

### What exists

- Explicit user-created facts/preferences with source and sharing flag.
- Literal keyword retrieval through FTS5, with a top-result limit.
- Provider-specific conversation history, limited to twelve recent eligible messages.
- Context trimming by serialized character count; this is not an exact tokenizer budget.
- Transitive memory references: later replies retain provenance inherited from earlier context.
- Changed/deleted/unshareable memories invalidate dependent future history.
- Observations and corrections are not silently promoted to memory.

### Recommended evolution

Short-term memory remains the bounded conversation context, with expiration for any persisted temporary memory. Long-term facts/preferences remain explicit memory records. Episodic memory can use selected episode summaries; procedural memory can store user-reviewed workflow instructions, never authority to bypass approval.

Add owner, category, confidence, last access, optional expiry, correction/deletion state and content revision to structured memory. Preserve existing API fields through aliases/adapters until a deliberate versioned API change is approved.

For semantic retrieval, a separate `memory_embeddings` table should store the memory/owner ID, model identifier/version, dimensions, content revision, vector and creation time. PostgreSQL's extension is named `vector`; the Python integration package alone does not enable it on the server.

Choose an embedding model and matching vector dimensions deliberately. A model change can require a new embedding space, re-embedding and a migration/index change. Do not compare vectors produced by different models merely because their dimensions match.

Start with filtered exact similarity search for a small dataset. Introduce HNSW or another approximate index only after measuring data volume and recall. Apply owner, lifecycle, expiry and sharing restrictions within the authorized query; test filtered result quality as well as speed.

### Three separate permission decisions

1. **Cloud persistence:** whether the user's existing data may be uploaded to Supabase.
2. **Cloud LLM context:** whether particular content may be included in a hosted reasoning request.
3. **Cloud embedding generation:** whether content may be sent to an external embedding provider.

Existing `allow_remote=False` addresses hosted model retrieval, not cloud database residency. A local LLM with Supabase persistence is not an entirely offline system. Use explicit policy fields and user-visible documentation, and make an import review part of cutover. Tests should prove that disallowed content reaches neither hosted LLM nor hosted embedding requests, and that deleted/expired/revised memory does not survive through stale vectors or conversation history.

## 11. Recommended changes: what, why, files and tests

All work in this section requires subsequent approval. Paths beginning with a module name are under `src/nila/` unless otherwise stated.

| ID | What should change and why | Likely affected files | How to test |
| --- | --- | --- | --- |
| R1 | Introduce small concrete repositories to isolate SQL from business behavior while preserving transaction-sized operations. Avoid a generic persistence framework. | New `storage/repositories/`; existing domain `service.py` files; `agent/context.py`; audit route in `api/app.py`; `storage/queries.py` | Run the same behavior contracts before/after extraction; inject persistence failures and assert rollback with no extra execution |
| R2 | Add a Supabase PostgreSQL connection with TLS, bounded pool/connection/statement timeouts and redacted errors. Keep network I/O from blocking async request handling. | `storage/database.py`, `core/config.py`, `core/errors.py`, `core/runtime.py`, `pyproject.toml`, `uv.lock` | Dedicated test project; failed TLS/auth/network connections; pool exhaustion; concurrent API responsiveness; no secret-bearing diagnostics |
| R3 | Preserve `0001_foundation.py`; introduce one authoritative PostgreSQL migration history with UUID/TIMESTAMPTZ/JSONB and explicit grants/RLS. Run upgrades as a deployment action, not normal startup. | Existing migration preserved; new packaged PostgreSQL migration directory; `storage/models.py`, `storage/database.py`, `core/runtime.py`, `cli/app.py` | Fresh schema, repeat upgrade, schema/model agreement, runtime DDL denial, compatibility rejection of wrong schema version, installed-package migration discovery |
| R4 | Add owner identity, owner-aware lookups, same-owner relationships and RLS. A plain `user_id` field without enforced authorization is insufficient. | `storage/models.py`, migrations, repositories, `core/schemas.py`, `api/app.py`, `core/runtime.py` | Two owners plus missing identity; read/insert/update/delete isolation; ownership reassignment and cross-owner FK denial; pooled identity leakage tests |
| R5 | Use a restricted non-owner runtime role without `BYPASSRLS`; separate migration credentials and keep SDK administrative secrets backend-only. Extend configuration aliases deliberately. | `core/config.py`, `core/credentials.py`, `.env.example`, migrations/grants, deployment documentation | Check actual role attributes/grants; normal operations succeed with restricted credentials; DDL/audit mutation fail; verify no credentials in API responses, logs or future frontend bundles |
| R6 | Translate approval consumption into a PostgreSQL row-lock/conditional-update protocol with stable claim identifiers and database-authoritative time. Preserve atomic audit insertion. | `permissions/service.py`, `automation/executor.py`, `automation/tools.py`, execution repository and migrations | Independent connections/processes race to consume the same approval; cancellation/revocation races; commit acknowledgement loss; no second tool call; atomic rollback on audit failure |
| R7 | Replace globally destructive startup recovery with worker/device ownership, leases and fencing. A fencing value lets the database reject completion from an obsolete worker. | `core/runtime.py`, `api/app.py`, `agent/service.py`, `automation/executor.py`, supporting lease schema/repository | Two instances, expired/live leases, heartbeat loss, stale completion, interrupted planning/chat, and no replay after unknown external outcome |
| R8 | Replace FTS5 with PostgreSQL full-text search before adding embeddings. Preserve useful query behavior and parameter binding. | `memory/service.py`, memory repository, `storage/models.py`, migrations | Existing Unicode/punctuation/update/delete scenarios on PostgreSQL; ranking and stop-word regression fixtures; no SQL/FTS syntax injection |
| R9 | Add memory lifecycle/revision fields and separate cloud-sharing permissions, preserving transitive context invalidation. | `storage/models.py`, `core/schemas.py`, `memory/service.py`, `agent/context.py`, `llm/base.py`, migrations, permission documentation | Revision/expiry/correction/deletion tests; dependent history exclusion; outbound provider spies; import old context-reference snapshots |
| R10 | Introduce model-specific embeddings in a later phase, with independent provider selection and stale-vector invalidation. | New `memory/embeddings.py`, embedding repository, vector migration; dependency/config updates when implemented | Deterministic test vectors, wrong dimensions/model rejection, owner isolation, revoked sharing, deletion/expiry and content-revision mismatches |
| R11 | Preserve the audit stream and constrain ordinary runtime mutation. Normalize database/API errors before they can disclose SQL parameters or credentials. | Audit repository, migrations/grants, `core/errors.py`, `api/app.py`, `storage/database.py` | Audit append succeeds with state transition; update/delete denied to ordinary role; failure messages and captured logs are redacted |
| R12 | Add a dedicated lazy Supabase SDK factory for service APIs. Introduce Auth, private Storage and Realtime only when their application features need them. | New `storage/supabase_client.py`; `core/config.py`, `core/runtime.py`; future feature modules | Mock SDK failures/timeouts first; later integration tests under real user-scoped permissions, private bucket access, token expiry and Realtime authorization |
| R13 | Plan reviewed, resumable import/cutover rather than silently converting a live file. Preserve source IDs, relationships, timestamps and historical approval payloads. | Future import utility, PostgreSQL migrations, CLI migration commands, setup/runbook docs | Restore a backup copy; reconcile counts/relationships/digests; interrupted import/retry without duplicates; preserve source; handle new target writes before rollback |
| R14 | Later add React and a device-scoped Windows executor while keeping permission enforcement authoritative in FastAPI/database transactions. Realtime notifications are hints, not execution authority. | Future `frontend/` and desktop-agent module; existing API/executor contracts | UI approval preview tests, expired/wrong-device claims, duplicate notifications, disconnect/reconnect, revoked permissions and local execution result reconciliation |
| R15 | Keep RL as a separate Python pipeline consuming explicitly selected/versioned experience data. Evaluated policies remain subordinate to tool permissions. | Later learning dataset/evaluation/training modules and schema; existing `learning/service.py` preserved | Fixed dataset splits, reproducible rewards/metrics, policy-version provenance, independent evaluation and tests showing policies cannot approve their own actions |

### Security implementation notes for the future phase

- For the first single-owner backend, trusted FastAPI configuration/authentication can map to a fixed application owner. Never trust a request-supplied owner ID.
- Set ownership context transaction-locally when using pooled PostgreSQL connections; test cleanup on both commit and rollback. A direct SQL connection does not automatically inherit a Supabase user's JWT claims.
- Enable RLS on user-owned/exposed tables and review table/function grants as well as policies. Enabling RLS does not protect operations performed by a bypass role.
- A dedicated runtime role should not own the tables or have broad administrative privileges. Secret/service-role SDK keys bypass normal RLS and are not proof that user isolation works.
- Keep sensitive application data in a deliberately configured schema; expose only required objects through the Data API. Prefer invoker permissions for functions. Any privileged function needs narrow execution grants, a fixed search path and explicit authorization tests.
- Supabase Auth is needed before remote/multi-user/mobile access, not merely because the current local backend uses managed PostgreSQL. Verify tokens and map identity server-side at that milestone.
- Keep model/database credentials in backend environment/secret configuration. API keys, database connection passwords and application signing secrets are distinct. No privileged value belongs in a frontend `VITE_*` variable or a distributed desktop/Android bundle.
- Use separate development, test and production projects/credentials. A future integration suite must refuse an unapproved production target rather than create/drop fixtures there.

### Minimal future dependencies

No dependencies were added in Phase A. For an approved database milestone, evaluate `supabase` and `psycopg[binary]` alongside the existing SQLAlchemy/Alembic stack. Add the Python `pgvector` integration when vector support is implemented. Resolve shared HTTPX/Pydantic constraints against the current lockfile rather than guessing compatible versions.

The PostgreSQL driver is a client library, not a local server installation. A Supabase session-pooler connection is appropriate to evaluate for the persistent Windows backend when IPv6 direct access is unavailable. Transaction-pooler modes have different prepared-statement/session-state limitations; do not assume a session advisory lock or session-level identity setting survives transaction pooling.

React/TypeScript/Vite/Tailwind and Vitest/React Testing Library belong to the later frontend milestone. PyTorch, Gymnasium and Stable-Baselines3 remain deferred until a real training/evaluation task uses them.

## 12. Missing tests and evidence limits

Passing tests cover important boundaries, but no coverage percentage was measured and not every endpoint/failure branch is exercised.

| Gap | Why it matters | Suggested location / future test |
| --- | --- | --- |
| PostgreSQL locks and RLS | SQLite and same-runtime coroutine tests cannot establish PostgreSQL semantics | New PostgreSQL integration module; separate connections/processes and two-owner roles |
| Claim/audit transaction failure | A partial write must not authorize execution | `test_permissions.py` / execution repository tests; injected exception before commit, assert no consumption or tool call |
| Lost commit acknowledgement | A timeout does not establish whether authorization was committed | New persistence-failure tests; stable claim ID reconciliation and conservative outcome handling |
| Multi-instance recovery and fencing | Current filelock test protects one directory on one machine | Lease tests with different local directories sharing a test database; active work must survive another startup |
| Successful multi-step ordering and direct out-of-order execution | Existing two-step tests focus on cancellation and step limits | Extend execution tests with all-step success, rejected early execution of step two, and exactly one call per step |
| Concurrent approve/renew/revoke/cancel | Existing tests mostly check these states sequentially | Race tests with independent transactions and controlled synchronization |
| Model timeout/cancellation and malformed structured output | Provider exception and tool-timeout tests do not cover every model exit path | `test_failures.py`, `test_openai_adapter.py`; empty/refused/incomplete/malformed plans and cancellation |
| Consent collection/revocation races | Sequential invalid-consent tests do not prove concurrent revocation behavior | `test_permissions.py`; transaction ordering and no collection after effective revocation |
| Backup/import/restore fidelity | Current storage test checks fresh/repeated migrations, not data transfer | Legacy fixture dataset including relationships, Unicode, JSON nulls, timestamp precision and approval payloads |
| Memory correction/expiry and embedding invalidation | Expiry, vectors and explicit revisions do not yet exist | Extend context/storage tests as those features are introduced |
| Export file safety and completeness | Export exists but is not a complete database backup and lacks dedicated file tests | CLI tests using new temp paths; no overwrite, UTF-8 round-trip, complete memory pagination |
| Credential/configuration failures | Test credentials are synthetic; the OS credential store was not exercised | Unit tests mocking unavailable store, malformed configuration, secret redaction and alias precedence |
| Cloud upload consent | Existing sharing flag has no cloud-database-residency meaning | Import/policy tests proving records are not uploaded solely because an SDK/DSN is configured |
| Log immutability and retention | Current audit is not enforced append-only in the database | Restricted-role integration tests; preserve audit through permitted resource deletion |
| Supabase Auth/Storage/Realtime, UI and actual desktop tools | These features are absent | Add feature-specific tests only when implemented; no fabricated Phase A coverage |

## 13. Phased implementation plan after approval

| Phase | Scope and rationale | Files / verification gate |
| --- | --- | --- |
| A - completed here | Inspect, run the unchanged baseline, record findings and preserve existing work | This report; 35 passed, 1 warning; source/config hash agreement |
| B1 - persistence seam | Preserve a checkpoint, define owner/transaction contracts, extract a few concrete repositories without changing existing behavior | Existing service/storage modules and contract tests; current baseline stays green |
| B2 - Supabase foundation | Add managed PostgreSQL connection, dedicated SDK boundary, separate migration/runtime credentials, owner schema and tested RLS | New PostgreSQL migrations/config/client; approved test-project integration, role and schema checks |
| B3 - execution correctness | Port atomic claims, cancellation, logs and scoped recovery; introduce execution ownership/leases before shared workers | Execution/permission/runtime modules; cross-connection/process races, failure injection and stale-worker tests |
| B4 - verified cutover | Back up/import actual data if present, reconcile it, review upload consent, switch one authoritative write target | Import/runbook artifacts; source preserved, counts/FKs/digests/context verified and rollback procedure documented |
| C - semantic memory | Add lifecycle/revision metadata and embedding storage/provider integration after lexical retrieval works on PostgreSQL | Memory/context/vector changes; compatibility, sharing, expiry and retrieval-quality tests |
| D - dashboard and multi-device services | Add React UI; Auth before remote access; private Storage and authorized Realtime when used | Frontend/API/auth/storage modules; user/device isolation and UI approval tests |
| E - local execution | Introduce a Windows agent with narrowly scoped approved tools and explicit partial/unknown outcomes | Device/automation modules; wrong-device/expired/replayed requests denied, no command execution from notifications alone |
| F - evaluated learning | Build selected experience datasets and separate training/evaluation/versioning; deploy only evaluated policies through the existing permission boundary | Learning modules and later RL tables; reproducibility, held-out evaluation, rollback and permission-invariance tests |

Supabase remains the persistent data platform through these phases. Long-running reasoning, RL training and local desktop automation do not run inside database operations. Retain the current CLI and modular backend throughout the transition.

## 14. Conclusion and next approval

The baseline is healthy within its documented single-user, SQLite, dry-run scope. The existing features and tests should be evolved rather than replaced. There is no evidence from this run of a failing application test or a damaged runtime database; no configured runtime database was present to inspect.

The recommended next step is a narrowly scoped **B1 persistence-boundary and transaction-contract change**, followed by separately verified Supabase configuration/schema work. The PostgreSQL locking, ownership/RLS, recovery and cloud-consent requirements are prerequisites to a trustworthy cutover, not optional cleanup afterward.

No recommendation in this report has been implemented. Stop at Phase A and obtain approval before application, dependency, environment, database, frontend or automation changes.
