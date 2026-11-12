# NILA AI - Phase B1 Persistence Seams and Transaction Contracts

**Date:** 2026-11-12  
**Scope:** Application persistence boundaries, database-independent transaction rules, ownership and privacy designs  
**Status:** B1 code and tests complete; no Supabase connection, schema, dependency, environment, or data migration was added

## 1. What this phase changed and why

Before B1, application services talked directly to SQLAlchemy sessions. SQLite-specific rules were mixed into general code: `BEGIN IMMEDIATE` lived in the database helper, the FTS5 query lived in the memory service, and the API read audit rows directly. That works for one local SQLite process, but it makes a future PostgreSQL migration risky: it is hard to see which behavior is business policy and which behavior is a SQLite implementation detail.

B1 adds a narrow persistence boundary:

```text
CLI / FastAPI
     |
     v
Application services: workflow, validation, model/tool orchestration
     |
     v
Repositories: intent-level persistence operations, one transaction each
     |
     v
Database + DatabasePolicy: SQLite today, PostgreSQL later
```

The most important guarantees remain unchanged:

- An approval is single-use.
- An action cannot execute before earlier actions succeed.
- The approval is consumed before an external tool starts.
- A consumed or expired approval cannot be replayed.
- Interrupted work is never automatically re-executed.

The only intentional behavior hardening is that a stale worker can no longer record a completion after recovery has marked its action interrupted. This makes the recovery contract explicit and testable instead of relying on timing.

**Beginner note:** a "repository" is not a second database or a new framework. It is simply a class that owns the database operations for one part of the application. The service asks the repository to do something meaningful, such as "claim this approved action", instead of writing database queries itself.

## 2. Checkpoint and preservation

A local Git checkpoint was created before source changes:

```text
60442ba Document Phase A baseline and migration readiness
9715fc5 Initial commit - Nila AI
```

The checkpoint contains the Phase A report. It is a local commit; it was not pushed. The B1 source changes are intentionally left uncommitted for review and approval. No existing application database, credential, environment file, migration, or user data was changed.

The earlier Phase A report (including the 35-test baseline) remains in `docs/PHASE_A_BASELINE_REPORT.md`. Existing behavior was verified again before adding new tests: **35 passed, 1 warning**.

## 3. Current architecture after B1

### Module boundaries

| Module | Responsibility |
| --- | --- |
| `api` | Local authentication, endpoint contracts, process lifetime |
| `cli` | User commands, approval previews, HTTP client |
| `core` | Settings, DTOs, errors, digests, service composition |
| `llm` | Provider protocol, demo provider, OpenAI adapter |
| `agent` | Bounded prompt construction and chat workflow |
| `memory` | Application-facing memory facade |
| `tasks` | Planning workflow and task inspection |
| `permissions` | Approval and consent workflow |
| `automation` | Tool registry, execution orchestration, action state machine |
| `observation` | Consented manual notes |
| `learning` | Feedback and descriptive evaluation |
| `storage.database` | Engine, sessions, transactions, audit append helper |
| `storage.dialects` | The only SQLite engine/connection/write-policy implementation |
| `storage.repositories` | Persistence boundaries for each domain area |
| `storage.models` | SQLAlchemy ORM models |
| `storage.queries` | Small shared read helpers (`require`, `task_view`, terminal states) |

Application layers (`agent`, `api`, `automation`, `core`, `learning`, `memory`, `observation`, `permissions`, `tasks`) no longer import SQLAlchemy or ORM models. A boundary test enforces this.

### Dependency direction

```text
api / cli
    |
    v
application services
    |
    v
storage.repositories
    |
    v
storage.database -> storage.dialects -> SQLite
    |
    v
storage.models
```

This direction matters: business services do not know whether the data is in SQLite or PostgreSQL. The future PostgreSQL adapter changes the policy and repository implementations, not the approval or execution rules.

## 4. New persistence boundaries

### `DatabasePolicy`

`src/nila/storage/dialects.py` defines the database-specific seam:

| Member | Purpose |
| --- | --- |
| `name` | Human-readable backend name |
| `create_engine(data_dir)` | Creates the SQLAlchemy engine |
| `configure_connection(connection)` | Applies connection settings |
| `begin_write(session)` | Starts the write transaction |

`SQLitePolicy` is the only implementation in B1. It owns the SQLite URL, `connect_args`, foreign-key PRAGMA, busy timeout, WAL mode, and `BEGIN IMMEDIATE`.

**Why:** these details are not business rules. A future `PostgresPolicy` can create a `postgresql+psycopg` engine and start an ordinary transaction, leaving the rest of the application unchanged. No PostgreSQL adapter or driver was added.

### Repositories

Each repository owns the database work for one area and opens its own transaction where it mutates state. This means "one repository method call" is the unit that either commits completely or rolls back completely.

| Repository | Boundary |
| --- | --- |
| `ConversationRepository` | Conversations, user/assistant messages, chat episodes |
| `MemoryRepository` | Memory CRUD, listing, search, context-state lookup |
| `TaskRepository` | Task creation, plan completion/failure, task views, cancellation |
| `ApprovalRepository` | Approval creation, expiry handling, deny/revoke |
| `ConsentRepository` | Consent grant, listing, revocation |
| `ObservationRepository` | Consent check plus observation insert/delete |
| `FeedbackRepository` | Target validation, feedback upsert, evaluation counts |
| `ExecutionRepository` | Action claim, completion, ordering checks, recovery |
| `AuditRepository` | Read-only audit listing for the API |

### `MemorySearch` strategy

The FTS5 query is now behind a tiny `MemorySearch` protocol:

- `SQLiteFTS5MemorySearch` owns the `memory_fts`, `MATCH`, and `bm25` SQL.
- `MemoryRepository` owns CRUD and transaction boundaries.
- `MemoryService` remains a thin application-facing facade.

**Why:** PostgreSQL will not use FTS5. It will use a text-search vector and index instead. Keeping the ranking/query implementation behind one strategy means the future switch does not require changing memory workflow code. The strategy has one implementation today; it was introduced because the SQL is genuinely dialect-specific, not as a general-purpose abstraction.

### What was deliberately not abstracted

- SQLAlchemy remains the ORM and query builder for portable operations.
- No generic `BaseRepository`, unit-of-work framework, dependency-injection container, or event bus was added.
- No new database tables, owner columns, or data migrations were added in B1.
- SQLite remains fully supported.
- The file lock remains a local process guard in `api/app.py`, not a database-level guarantee.

## 5. Transaction contracts

These requirements are written for any relational backend. SQLite currently implements them with one writer reservation; PostgreSQL must implement them with row locks and conditional updates.

### 5.1 General rules

1. A model or tool call never runs while a database write transaction is open.
2. State that authorizes an external action is committed before the action starts.
3. A failure that changes policy state (expired, invalidated, deadline exceeded) commits that state change, then raises the user-visible error.
4. A precondition failure that changes no state (not found, wrong status, ordering violation) rolls back and raises.
5. Audit events are written in the same transaction as the state transition they describe.
6. Repository methods that return a view have finished their transaction first; callers do not hold lazy ORM objects across transactions.
7. No automatic retry executes a tool. A retry of a request may observe a committed "running" or terminal state, but must not repeat the side effect.

### 5.2 Approval creation and validation

`ApprovalRepository.approve(action_id, digest, ttl_seconds)`:

- Loads the action and its task.
- Rejects terminal tasks and actions not in `proposed` or `expired`.
- Recomputes the canonical action digest from task ID, task revision, action position, tool, tool version, and arguments.
- Uses a constant-time comparison with the submitted preview digest.
- Rejects a digest that does not equal the stored action digest.
- Rejects an already-consumed approval.
- Sets the approval digest and expiration and marks the action `approved`.
- Marks the task `ready` only when every action is `approved` or `succeeded`.
- Writes the audit event in the same transaction.

**Why:** the user approves an exact action. If arguments, tool, position, or task revision change after the preview, the approval must become useless rather than silently authorizing a different action.

### 5.3 Approval expiration

At approval time, an unused previously approved but expired record may be renewed.

At execution-claim time, `now >= expires_at` means:

```text
action: approved -> expired
task:   -> awaiting_approval
audit:  approval_expired
```

That transaction commits before the error is returned. No tool runs. The user must review and approve again. Re-approval creates a fresh expiration window on the same digest.

### 5.4 Approval denial and revocation

- Deny is allowed for `proposed` or `expired`.
- Revoke is allowed only for `approved`.
- A terminal task cannot be denied or revoked.
- Denying/revoking marks the action `denied`/`revoked`, cancels the task, cancels other pending actions, and writes audit metadata.

A running action cannot be revoked through this path. Cancellation during a running step records the actual result; it does not pretend to undo work already started.

### 5.5 Single-use execution claim

`ExecutionRepository.claim(action_id, timeout_seconds, validate)` performs one write transaction:

```text
1. Load action and task.
2. Reject terminal task.
3. Reject action.status != approved.
4. Reject unless every earlier action is succeeded.
5. Load approval; reject missing or already consumed.
6. Compute current digest and remaining task deadline.
7. Reject expired / altered / deadline-exceeded states (commit those transitions, then return the error).
8. Re-validate tool and arguments inside this transaction.
9. Set approval.consumed_at.
10. Set action = running, task = running, set task.started_at if first step.
11. Insert a running action episode.
12. Append action_started audit metadata.
13. Commit.
14. Return the captured tool, validated arguments, attempt episode id, and remaining deadline.
```

The executor uses the returned captured arguments. It does not re-read mutable action arguments after the authorization transaction.

**Guarantee today:** SQLite's `BEGIN IMMEDIATE` serializes the read/check/write sequence, so two local requests cannot both consume the same approval. A new test also verifies this across two independent service instances using the same database file.

**Guarantee required from PostgreSQL:** the same sequence must be serialized per action/task using row locks, plus a conditional approval update as a backstop. See section 5.9.

### 5.6 Completion

`ExecutionRepository.complete(...)`:

- Loads the action, task, and attempt episode.
- **Requires the action to still be `running`.** If recovery or another authoritative process changed it to `interrupted`, completion is rejected with a conflict and the result is not recorded.
- Records the action result/error and status.
- Marks the episode completed and records a simulated outcome.
- Updates task state unless the task was cancelled:
  - all actions succeeded -> `succeeded`
  - all actions approved/succeeded -> `ready`
  - otherwise -> `awaiting_approval`
- Appends `action_finished` audit metadata in the same transaction.

**Why the `running` guard:** a worker may lose its ability to commit, be declared stale by recovery, and later wake up. Recording its late result over an `interrupted` state would misrepresent what the system knows. The current guard is optimistic and works for SQLite. PostgreSQL should make the final update conditional on the claim/attempt identity as well.

### 5.7 Ordering and duplicate execution

- Actions have unique `(task_id, position)`.
- A claim requires every earlier position to be `succeeded`.
- Only one action per task can be runnable at a time in normal flow.
- An approval can be consumed once.
- A retry after a successful claim sees `consumed_at` and is rejected.
- A timeout/failure consumes the approval and ends the attempt; it is not automatically retried.

**Not yet guaranteed:** a real external effect and the database result cannot be committed atomically. A crash after the effect but before completion leaves an unknown outcome. B1 preserves the existing conservative rule: mark it interrupted and require review rather than replay. Future tool adapters must support idempotency keys or explicit outcome reconciliation.

### 5.8 Interrupted-work recovery

On service startup, `ExecutionRepository.recover_interrupted()` runs in one transaction:

- `planning` or `running` tasks -> `interrupted`
- `running` actions -> `interrupted`
- `running` episodes -> `interrupted`

This is intentionally conservative. It does not know whether an external effect occurred.

**Current limitation:** recovery scans the entire local database and assumes this service exclusively owns it. The local file lock prevents two API processes from using the same data directory, but that is not a distributed lease. PostgreSQL multi-worker recovery needs ownership/lease fields and fencing; B3 must not simply run this global scan in every worker.

### 5.9 PostgreSQL concurrency implementation plan

The future PostgreSQL claim transaction should use a fixed lock order to avoid deadlocks:

```text
task row -> action row -> approval row
```

Illustrative sequence:

```sql
BEGIN;
SELECT id, status, started_at FROM tasks WHERE id = :task_id FOR UPDATE;
SELECT id, status, position, digest, arguments FROM actions
 WHERE id = :action_id FOR UPDATE;
SELECT id, digest, expires_at, consumed_at FROM approvals
 WHERE action_id = :action_id FOR UPDATE;

-- Re-check state, expiration, ordering, and digest under the locks.
SELECT count(*) FROM actions
 WHERE task_id = :task_id AND position < :position AND status <> 'succeeded';

UPDATE approvals SET consumed_at = :now
 WHERE id = :approval_id AND consumed_at IS NULL;
-- Require exactly one updated row.

UPDATE actions SET status = 'running' WHERE id = :action_id AND status = 'approved';
-- Require exactly one updated row.

UPDATE tasks SET status = 'running', started_at = coalesce(started_at, :now)
 WHERE id = :task_id;
INSERT INTO episodes (...) VALUES (...);
INSERT INTO audit_events (...) VALUES (...);
COMMIT;
```

Requirements beyond the simple query:

- Approval creation, denial, revocation, cancellation, claim, and completion must participate in the same lock protocol so they cannot race the checks.
- Prefer database/server time for expiration and leases to avoid client clock skew.
- A conditional update is a backstop, not a substitute for correct locking.
- If a commit acknowledgement is lost, the client must read the durable approval/action state before retrying; it must not assume rollback.
- Completion should be conditional on the same attempt/lease identity, not only on `status = 'running'`, once leases exist.
- Readers may use ordinary snapshots. Writers that change policy state must use the locking protocol.
- Keep tool execution outside the database transaction.

These PostgreSQL details are a design target. They were **not implemented or tested** in B1 because no PostgreSQL server or driver is part of this phase.

## 6. Ownership strategy

### Current state

- All primary keys are random 32-character UUID hex strings.
- `messages` reference a conversation and episode.
- `actions` reference a task; `approvals` reference an action.
- `observations` reference consent; feedback references a target by type and ID.
- `episodes` reference a resource polymorphically through `kind` + `resource_id`.
- There is no `owner_id`, user table, or RLS policy.
- The local API token identifies "the local operator", not a distinct cloud user.

### Proposed ownership model

B1 does not add owner columns, because that would require a speculative local schema migration and would start B2's database work early. The repository seam makes the later change containable.

Proposed root ownership:

| Root record | Owner source |
| --- | --- |
| `memories` | `owner_id` |
| `conversations` | `owner_id` |
| `tasks` | `owner_id` |
| `consents` | `owner_id` |
| `users` | New application table; optional unique link to a Supabase Auth subject |

Child ownership:

| Child | Ownership rule |
| --- | --- |
| `messages` | Same owner as parent conversation |
| `actions` | Same owner as parent task |
| `approvals` | Same owner as parent action/task |
| `observations` | Same owner as consent |
| `feedback` | Same owner as its validated target |
| `episodes` | Owner recorded explicitly when introduced, because the target can be a conversation, task, or action |
| `audit_events` | Server-scoped; not exposed as normal user content |

Two viable RLS approaches:

1. **Parent-join policies:** `owner_id` exists only on roots; child access uses `EXISTS` against the parent. This avoids duplicated owner values but makes policies and large queries more complex.
2. **Denormalized owner:** add `owner_id` to child tables and enforce consistency with the parent. This gives simpler, faster policies and clearer ownership checks, at the cost of keeping the columns consistent.

For a small personal assistant, the Phase A direction recommends starting with root ownership and adding denormalized owner IDs to message/action/approval/episode rows in B2 when the PostgreSQL schema is created. That decision should be made together with the actual RLS policy and index design, not by adding columns blindly now.

### Server-side principal resolution

The future principal must be resolved by the backend, never supplied as a request field:

- Local mode: a fixed application owner ID (for example, the existing single local operator).
- Cloud mode later: verify the Supabase JWT server-side, map its subject to an application user, and set a transaction-local owner context.
- Every repository query that returns user data must include the owner scope, including lookup by globally unique ID.
- Cross-owner parent references must be rejected by constraints and tested.
- A pooled database connection must not leak a previous request's owner context.

RLS is not sufficient by itself: normal runtime credentials must not own tables or have `BYPASSRLS`. The service-role key is an administrative credential, not a substitute for user-scoped policies.

### Migration rule

Existing rows must be assigned to the local owner during an explicitly approved B2/B4 step. **Do not upload local memories merely because a Supabase connection is configured.** The import must be previewed, consented to, and reconciled. Keeping a source backup is mandatory.

## 7. Privacy permission model

B1 does not change privacy behavior. It defines the vocabulary so future work does not accidentally merge unrelated permissions.

There are four independent decisions:

| Permission | Question it answers | Existing representation |
| --- | --- | --- |
| Cloud persistence | May this information be stored in Supabase? | None yet. Local SQLite storage is not a cloud-persistence consent. |
| Cloud LLM context | May this content be sent to a hosted reasoning model? | `Memory.allow_remote` plus `provider.remote`; history is filtered by the same rule. |
| Cloud embedding | May this content be sent to an external embedding provider? | None yet; no embeddings exist. |
| Local observation | May NILA record a manual note or, later, observe local activity? | `Consent` scope `manual_observation` with expiry/revocation. |

### Independence rules

1. `allow_remote=True` does **not** mean the memory may be uploaded to Supabase. It only permits hosted-LLM context.
2. Cloud persistence does **not** imply permission to send content to a cloud LLM or embedding provider.
3. Cloud LLM permission does **not** imply permission to create embeddings in the cloud.
4. Local observation consent does **not** imply any cloud permission.
5. A future embedding provider permission does **not** imply LLM context permission.
6. Deleting or revoking one permission does not silently grant another.

Examples:

| Situation | Allowed behavior |
| --- | --- |
| Supabase persistence = yes, cloud LLM = no | Store rows in Supabase; use demo/local reasoning only. |
| Cloud LLM = yes, Supabase persistence = no | Use eligible memory in a hosted request without uploading the database. The provider's own retention policy still applies; the OpenAI adapter uses `store=False` but that is not the same as database residency. |
| Embedding provider = yes, cloud LLM = no | Generate vectors through the embedding service; do not send content to the reasoning model. |
| Observation = yes, all cloud permissions = no | Record a local note; do not upload or embed it. |
| Cloud persistence = yes, observation = no | Persist existing authorized data; do not silently start observing the desktop. |

### No silent upload

- Existing local memory must not be imported automatically.
- Enabling Supabase configuration must not copy rows.
- `allow_remote=True` records must not be treated as import consent.
- A future cloud import must require an explicit user action, a preview/count of what will be uploaded, and a record of the consent used.
- Revocation must affect future use; it cannot retract a request already in flight.
- A future embedding vector is derived data and must be invalidated when its source memory is deleted, expired, corrected, or its sharing permission changes.

### Future enforcement points

- Memory repository: filter by persistence/LLM/embedding policy separately.
- Context builder: keep the existing remote filter, then add an explicit persistence-independent embedding path.
- Observation service: keep consent checks inside the observation transaction.
- Import command: add a separate one-time cloud-persistence action; never a side effect of connection setup.
- RLS: authorize data access by owner, not by privacy preference. Privacy choices are an additional application-level policy.

## 8. SQLite-to-PostgreSQL mapping

| SQLite behavior | Current location | PostgreSQL design target |
| --- | --- | --- |
| SQLite engine URL and connect args | `SQLitePolicy.create_engine` | `PostgresPolicy` creates a psycopg engine (dependency added later, not now) |
| `PRAGMA foreign_keys`, `busy_timeout`, WAL | `SQLitePolicy.configure_connection` | PostgreSQL foreign keys are native; configure lock/statement timeouts and pool limits instead of PRAGMAs |
| `BEGIN IMMEDIATE` | `SQLitePolicy.begin_write` | Ordinary transaction plus explicit `SELECT ... FOR UPDATE` and conditional updates |
| Database-wide single writer | SQLite engine | Row-level locking in a fixed order (`task -> action -> approval`); unique constraints as backstops |
| FTS5 virtual table and triggers | `0001_foundation.py` migration | `tsvector` content/column, trigger or generated column, GIN index |
| `MATCH`, quoted terms, `bm25()` | `SQLiteFTS5MemorySearch` | Parameterized `to_tsquery`/`websearch_to_tsquery`, `ts_rank_cd`; test Unicode and decide stemming/config explicitly |
| SQLite JSON text | SQLAlchemy `JSON` | `JSONB` with deliberate SQL NULL vs JSON null handling |
| Float Unix timestamps | Models and DTOs | `TIMESTAMPTZ`, explicit UTC serialization for legacy API fields |
| 32-character UUID hex IDs | `new_id()` | Native `UUID` while preserving existing values during import |
| Local `service.lock` file | `api/app.py` lifespan | Database lease/owner table plus a unique constraint; local file lock remains a fast local guard, not a distributed lock |
| In-memory busy-conversation set | `ChatService` | Database-backed conversation operation lease or a unique active-operation constraint |
| Automatic `migrate()` at startup | `build_services()` | Deployment-time migration with migration credentials; runtime only verifies schema version |
| Global startup recovery | `ExecutionRepository.recover_interrupted` | Per-worker leases/fencing; never mark another live worker's work interrupted |
| `require()` and ORM queries | `storage/` | Portable SQLAlchemy; add row locks and owner predicates in repository methods |
| FTS synchronization triggers | Migration | PostgreSQL trigger or application-maintained `tsvector`; test update/delete consistency |

The API's JSON contract (float timestamps, string IDs, `allow_remote`) should be preserved through a compatibility layer during migration. Changing storage types must not silently change the CLI or API wire format.

## 9. Files changed

### New source files

- `src/nila/core/integrity.py` - canonical action digest, shared by task, approval, and execution persistence.
- `src/nila/storage/dialects.py` - `DatabasePolicy` protocol and the only `SQLitePolicy` implementation.
- `src/nila/storage/repositories/__init__.py` - repository exports.
- `src/nila/storage/repositories/approvals.py` - approval lifecycle.
- `src/nila/storage/repositories/audit.py` - audit reads.
- `src/nila/storage/repositories/consents.py` - consent lifecycle.
- `src/nila/storage/repositories/conversations.py` - conversations, messages, chat episodes.
- `src/nila/storage/repositories/execution.py` - claim, completion, ordering, recovery.
- `src/nila/storage/repositories/feedback.py` - feedback and evaluation.
- `src/nila/storage/repositories/memory.py` - memory CRUD and the FTS5 strategy.
- `src/nila/storage/repositories/observations.py` - consented observation persistence.
- `src/nila/storage/repositories/tasks.py` - planning and task lifecycle persistence.

### New test files

- `tests/integration/test_persistence_contracts.py` - claim-before-tool, cross-service single-use, ordering, stale completion.
- `tests/unit/test_persistence_boundaries.py` - source-level isolation of SQLite-specific behavior.

### Modified files

- `src/nila/storage/database.py` - delegates engine creation, connection setup, and write begin to the policy.
- `src/nila/automation/tools.py` - re-exports the digest from `core.integrity`.
- `src/nila/automation/executor.py` - workflow only; claim/completion delegated to the execution repository.
- `src/nila/agent/context.py` - context reads through conversation and memory repositories.
- `src/nila/agent/service.py` - chat workflow uses the conversation repository.
- `src/nila/memory/service.py` - thin facade over `MemoryRepository`.
- `src/nila/tasks/service.py` - planning workflow delegates persistence.
- `src/nila/permissions/service.py` - approval/consent workflow delegates persistence.
- `src/nila/observation/service.py` - delegates to the observation repository.
- `src/nila/learning/service.py` - delegates to the feedback repository.
- `src/nila/core/runtime.py` - composes repositories and services; recovery lives in the execution repository.
- `src/nila/api/app.py` - audit endpoint uses the audit repository.

### Documentation

- `docs/PHASE_B1_PERSISTENCE_DESIGN.md` - this document.

No `.env`, dependency, lockfile, migration, or database file was changed. The only Git checkpoint created before B1 was `60442ba`; B1 changes remain uncommitted.

## 10. Tests executed and exact results

### Baseline preservation

Command, from the repository root:

```powershell
& '.\.venv\Scripts\python.exe' -B -m pytest -p no:cacheprovider --basetemp 'C:\Users\bhara\AppData\Local\Temp\opencode\nila-b1-20261112-preserve' -ra
```

Result:

```text
35 passed, 1 warning in 26.77s
PytestExitCode: 0
```

All 35 original tests passed before the new contract tests were added.

### Final full suite

Command:

```powershell
& '.\.venv\Scripts\python.exe' -B -m pytest -p no:cacheprovider --basetemp 'C:\Users\bhara\AppData\Local\Temp\opencode\nila-b1-20261112-final2' -ra
```

Result:

```text
41 passed, 1 warning in 26.50s
PytestExitCode: 0
```

Breakdown:

| Test module | Passed |
| --- | ---: |
| `tests/acceptance/test_live_cli.py` | 1 |
| `tests/integration/test_api_workflow.py` | 4 |
| `tests/integration/test_failures.py` | 5 |
| `tests/integration/test_openai_adapter.py` | 2 |
| `tests/integration/test_permissions.py` | 14 |
| `tests/integration/test_persistence_contracts.py` | 4 |
| `tests/integration/test_storage.py` | 3 |
| `tests/unit/test_cli.py` | 2 |
| `tests/unit/test_context.py` | 4 |
| `tests/unit/test_persistence_boundaries.py` | 2 |
| **Total** | **41** |

The one warning is the existing Starlette/HTTPX development dependency deprecation:

```text
StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
```

### Lint and type checks

```text
ruff check src tests
All checks passed!

mypy
Success: no issues found in 50 source files
```

### What the new tests prove

1. The execution claim transaction commits before the tool executes: the action is `running`, the approval is consumed, and exactly one action episode exists while the tool is still blocked.
2. Two independent service instances sharing one SQLite database cannot both consume one approval; the tool runs once.
3. Action two cannot execute before action one succeeds.
4. A service restart that recovers an in-flight action prevents the stale worker from recording a late result.
5. `BEGIN IMMEDIATE`, the SQLite engine URL, and FTS5 SQL are confined to the intended storage modules.
6. Application packages do not import SQLAlchemy or ORM models.

## 11. Remaining limitations and future PostgreSQL tests

These are intentionally unresolved in B1:

- No PostgreSQL connection, driver, schema, migration history, RLS policy, or Supabase project configuration exists yet.
- Row-locking and conditional-update behavior has not been executed against PostgreSQL. The integration tests for those rules must run on a dedicated PostgreSQL test database in B2/B3.
- Global startup recovery still assumes one service owns the database. Multi-worker leases and fencing are B3 work.
- The in-memory busy-conversation set is process-local. Multiple API workers need a database-backed operation lease or constraint.
- Completion checks that the action is still `running`, but a future lease/attempt identity must prove the completing worker owns the exact attempt.
- There is no exactly-once external side-effect guarantee. Unknown outcomes remain interrupted and require review.
- Owner columns, user records, owner-scoped queries, and RLS are designed here but not implemented.
- Privacy permissions are documented only. There is no cloud persistence or embedding consent field yet.
- No data import or cutover utility exists. Existing local data must not be uploaded automatically.
- SQLite FTS5 behavior, PostgreSQL text-search configuration, Unicode/Tamil handling, stop words, and ranking equivalence are not yet validated.
- Float timestamps and string UUIDs remain the API representation; PostgreSQL-native types will require a compatibility review.
- Database time is not yet authoritative for approvals/leases; B1 still uses application `time.time()`.
- Automatic migration at startup remains for current SQLite use. Deployment-only migrations are a B2 requirement.
- No frontend, desktop automation, RL training, or real tool execution was added.

Future PostgreSQL integration tests must cover at minimum:

- Two connections racing to claim one approval; exactly one claim succeeds.
- Concurrent approve/revoke/cancel/complete transitions.
- Lost commit acknowledgement and reconciliation.
- RLS with two owners, including cross-owner ID guesses and parent-child references.
- Missing owner context and pooled-connection context leakage.
- Recovery with two workers where one worker's live lease must not be stolen.
- FTS/Unicode/punctuation/update/delete/ranking behavior.
- Import reconciliation for IDs, relationships, timestamps, JSON nulls, and approval digests.

## 12. Approval gate

Phase B1 stops here. The persistence boundaries, transaction rules, ownership strategy, and privacy model are ready for review. No Phase B2 work should begin until this document and the uncommitted source changes are approved.
