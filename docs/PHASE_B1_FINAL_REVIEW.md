# NILA AI - Phase B1 Final Independent Review

**Review date:** 2026-11-12  
**Checkpoint reviewed:** `60442ba` through B1 commit `dcb0171` (`phase1`), containing the reviewed B1 paths  
**Scope:** Independent review only. This review did not change application source, tests, dependencies, migrations, environment, or databases, and did not commit, amend, push, or revert anything.  
**Verdict:** The reviewed B1 code is technically suitable as a **SQLite-only persistence refactor**. No critical or high-severity behavioral regressions were found. Two medium review items and the documented PostgreSQL risks should remain explicit follow-ups; this is not a PostgreSQL-ready implementation. A process note applies because B1 became committed and reachable through the local `origin/main` tracking ref during this review.

## 1. Executive summary

B1 extracts persistence into repositories, isolates the SQLite engine and write policy, moves the FTS5 implementation behind a strategy, and adds a stale-completion guard. The existing HTTP API, CLI, service methods, persistence schema, and dry-run execution behavior remain intact.

- Final suite: **41 passed, 1 warning in 30.38s**, exit `0`.
- Ruff: **all checks passed**, exit `0`.
- Mypy: **success, 50 source files**, exit `0`.
- The original 35 tests remain unchanged and all pass; 6 new tests were added.
- No existing test file, dependency, lockfile, migration, `.env` file, or application database was changed.
- An independent two-thread claim probe using a disposable SQLite database produced exactly one `ActionClaim` and one `DomainError`, confirming that the claim transaction serializes simultaneous claims.
- The main review caveat is test evidence: the committed “concurrent” tests do not actually overlap claim transactions because the synchronous claim runs before the first `await`. The implementation passed the independent probe, but the suite should gain a true concurrent regression test.

### Review-process note

The review began with the B1 source, tests, and design document uncommitted. By the time this report was written, commit `dcb0171` (`phase1`) contained all 27 B1 paths, and local `HEAD` and the local `origin/main` tracking ref both resolved to `dcb0171`. This review did not create, amend, push, or revert that commit; no network fetch was performed during the review. The reviewed file contents are the same B1 snapshot that was inspected and tested.

If B1 was required to remain uncommitted until this review was accepted, that approval gate was bypassed by an action outside this review. Confirm that the commit and tracking-ref state are intentional before beginning Phase B2, and decide separately whether any rollback or follow-up commit is required.

## 2. Findings

### Critical

None.

### High

None in the reviewed code.

### Process state (outside code severity)

#### P1. B1 was committed and the local tracking ref moved during the review

**Evidence:** The review started with B1 uncommitted. At report time `HEAD` was `dcb0171` (`phase1`), containing all 27 reviewed B1 paths, and local `origin/main` also resolved to `dcb0171`. This review did not create, amend, push, or revert that commit.

**Impact:** If B1 was required to remain uncommitted until this independent review was accepted, that approval gate was bypassed by an action outside this review. The code review result remains applicable because the reviewed contents match the commit. Confirm that the commit and tracking-ref state are intentional; otherwise decide separately on a rollback or follow-up commit. This report does not perform either.

### Medium

#### M1. Committed concurrency tests do not overlap the claim transactions

**Affected files:** `tests/integration/test_persistence_contracts.py:72-90`, `tests/integration/test_permissions.py:88-101`, `src/nila/automation/executor.py:24-38`

The tests named “concurrent” use `asyncio.gather` around two `Executor.execute` calls. `Executor.execute` calls the synchronous `ExecutionRepository.claim` before its first `await` at the tool call. The event loop therefore completes the first claim transaction before scheduling the second coroutine. The second request sees the already-consumed approval and fails at the state check, not because two database claim transactions overlapped.

The tests still prove duplicate prevention and that the tool runs once, but they would pass even if `BEGIN IMMEDIATE` were not protecting an actual claim race.

**Independent review probe:** two OS threads, two service instances, one temporary SQLite database, and simultaneous `ExecutionRepository.claim` calls produced:

```text
results=['ActionClaim', 'DomainError']
claims=1 conflicts=1
action_status=running
```

The implementation appears to uphold the intended SQLite claim contract. **Recommendation:** add a committed thread- or process-based test with a barrier around the claim, or otherwise force a real overlap, before relying on this suite as proof of the PostgreSQL locking contract.

#### M2. Completion checks action status but not attempt or relationship identity

**Affected file:** `src/nila/storage/repositories/execution.py:110-142`

`complete()` requires the action to still be `running`, which is the intended B1 stale-worker guard and is covered by a test. It does not verify that:

- `action.task_id == task_id`;
- `episode.resource_id == action_id`;
- `episode.kind == "action"`;
- the episode being completed is the attempt represented by the claim.

The normal `Executor` path passes the IDs captured by `claim()`, and recovery changes the action to `interrupted`, so no current external API path reaches a false completion. This is a defense-in-depth and future-lease issue: a caller defect, a future lease reset, or a multi-worker attempt handoff could record a result against the wrong task or episode.

**Recommendation:** validate the relationships immediately, and add an explicit claim/attempt identity to the completion predicate when leases/fencing are implemented in B3.

### Minor

#### L1. Direct Python construction compatibility changed

**Affected files:** `src/nila/core/runtime.py:50-79`, service constructors in `src/nila/agent/service.py`, `src/nila/tasks/service.py`, `src/nila/permissions/service.py`, `src/nila/memory/service.py`, `src/nila/observation/service.py`, `src/nila/learning/service.py`, and `src/nila/automation/executor.py`

The documented HTTP API and CLI contract are unchanged. All public service method signatures are unchanged, `build_services` keeps its signature, and `action_digest` remains importable from `nila.automation.tools`. `Database(data_dir)` remains valid with the new optional policy.

The following direct-construction surfaces changed:

- `ChatService(db, settings, provider, context)` became `ChatService(settings, provider, context, conversations)`.
- `TaskService(db, ...)` became `TaskService(settings, ..., tasks)`.
- `Executor(db, settings, tools)` became `Executor(settings, tools, executions, tasks)`.
- `PermissionService(db, settings)` became `PermissionService(settings, approvals, consents)`.
- `MemoryService(db)`, `ObservationService(db)`, and `LearningService(db)` now take repositories.
- `ContextBuilder(db, settings, memory, provider)` became `ContextBuilder(settings, memory, conversations, provider)`.
- `core.runtime.recover_interrupted(db)` was removed; recovery is now `ExecutionRepository.recover_interrupted()`.
- `Services` gained a required `audits` field.

No in-repository code outside the composition root directly constructs these services. This is not a runtime or API regression, but the change should be documented if direct Python embedding is supported.

#### L2. Boundary and rollback tests have blind spots

**Affected file:** `tests/unit/test_persistence_boundaries.py:16-34`

The boundary test checks exact strings for `BEGIN IMMEDIATE`, `memory_fts`, `URL.create("sqlite"`, and direct SQLAlchemy imports. It does not catch other SQLite-specific constructs such as `PRAGMA`, `AUTOINCREMENT`, SQLite JSON functions, or equivalent SQL hidden behind different strings. The manual review found SQLite-specific SQL only in `src/nila/storage/dialects.py`, `src/nila/storage/repositories/memory.py`, and the existing migration, so there is no current violation.

The new tests also do not inject a repository/audit failure to prove rollback and absence of a tool call. The transaction structure is correct on inspection, but a fault-injection regression test would strengthen the transaction contract.

#### L3. Architecture documentation is now partly stale

`docs/architecture.md` still describes persistence as direct SQLAlchemy access and places recovery in `core`. The new `docs/PHASE_B1_PERSISTENCE_DESIGN.md` is accurate, but the older architecture guide should be reconciled in a documentation-only follow-up so future work does not reintroduce the pre-B1 design.

#### L4. B1 design document has trailing whitespace

`git diff --check 60442ba` (and `git show --check HEAD`) flags trailing whitespace on `docs/PHASE_B1_PERSISTENCE_DESIGN.md:3-4`. This is cosmetic and documentation-only, but it means the committed B1 snapshot does not pass a whitespace check against the checkpoint. Source files and tests have no whitespace errors.

## 3. Compatibility review

### Preserved contracts

- All documented FastAPI routes and request/response DTOs are unchanged.
- `GET /audit` has the same response shape and ordering; it now delegates to `AuditRepository`.
- CLI commands are unchanged.
- Public service methods remain compatible:
  - `MemoryService.create/update/delete/list_memories/search`
  - `ChatService.chat/history`
  - `TaskService.plan/get/list/cancel`
  - `PermissionService.approve/refuse/grant_consent/list_consents/revoke_consent`
  - `Executor.get_action/execute/run_task`
  - `ObservationService.create/list/delete`
  - `LearningService.feedback/evaluation`
  - `ContextBuilder.build`
- `build_services(settings, *, provider=None, tools=None)` is unchanged.
- `Database` transaction, session, migration, audit, and close behavior is preserved.
- The action digest payload and constant-time comparisons are unchanged.

The full API workflow, live CLI acceptance test, provider failure tests, planning limits, approval lifecycle, cancellation, timeout, recovery, feedback, storage, and context tests all pass. No existing tests were edited.

## 4. Isolation review

- `src/nila/storage/dialects.py` is the only location for the SQLite engine URL, connect arguments, foreign-key/busy-timeout/WAL PRAGMAs, and `BEGIN IMMEDIATE`.
- The FTS5 query is confined to `SQLiteFTS5MemorySearch` in `src/nila/storage/repositories/memory.py`; the virtual table and triggers remain in the existing migration.
- A source scan found no SQLite-specific SQL in application packages outside the intended storage files.
- Application layers no longer import SQLAlchemy or ORM models.
- `MemoryRepository` still defaults to `SQLiteFTS5MemorySearch` regardless of the injected `DatabasePolicy`, and `Database.migrate()` still invokes the existing SQLite Alembic history. This is consistent with B1 being SQLite-only, but a `PostgresPolicy` alone would not make the application PostgreSQL-ready.

## 5. Transaction, approval, execution, and recovery review

### Transaction boundaries

- Repository mutations use `Database.transaction()`; successful calls commit, and exceptions roll back.
- No model call or tool call occurs while a write transaction is open.
- Claim commits the authorization state, approval consumption, running episode, and audit event before the tool starts.
- Completion writes the action result, task state, episode outcome, and audit event in one transaction.
- Planning and chat model calls occur outside persistence transactions.
- Returned views are Pydantic snapshots, so callers do not hold lazy ORM objects across transactions.

### Approval and execution

- Approval digests include task ID, revision, position, tool, tool version, and arguments.
- Approval and execution both use constant-time digest comparison and the stored action digest is rechecked.
- Claim rejects terminal tasks, unapproved actions, earlier non-succeeded actions, missing/consumed approvals, expired approvals, altered actions, and exceeded deadlines.
- Expiry/altered/deadline failures commit their policy state before returning the error.
- The approval is consumed before tool execution; captured validated arguments are passed to the tool.
- The existing tests cover approval replay, expiry, alteration, denial, revocation, cancellation, ordering, timeout, tool failure, and cancellation between steps.
- The independent thread probe confirmed one successful claim and one conflict under truly simultaneous calls.

### Completion and recovery

- Completion rejects an action that recovery or another authority changed away from `running`.
- Startup recovery marks planning/running tasks, running actions, and running episodes interrupted.
- The restart/stale-completion test passes: a recovered action cannot record a late result, and no automatic replay occurs.
- Recovery remains a global local-database scan protected by the API file lock; it is not a distributed lease. This is explicitly documented as a B3 concern.

## 6. Functional and security review

- The 35-test baseline behavior is preserved: memory CRUD/search/export, chat/context, planning, approval lifecycle, execution, consent, observations, feedback, evaluation, audit, authentication, restart persistence, and the live CLI.
- No schema, dependency, lockfile, migration, environment file, or application database was changed.
- No secret material was added to source or documentation. `secrets.compare_digest` is used for digest comparisons; FTS terms are bound parameters; audit events remain metadata-only; tool errors remain generic.
- The only warning is the pre-existing Starlette/HTTPX deprecation notice, not a test failure.
- `git diff --check HEAD` passes; `git diff --check 60442ba` exits `2` only because of the two trailing-whitespace lines in the committed B1 design document. Source and test changes have no whitespace errors.
- At report time the only working-tree entry was the untracked final-review report; the B1 source, tests, and design document were already contained in `dcb0171`.

## 7. Test evidence

### Final verification

```powershell
& '.\.venv\Scripts\python.exe' -B -m pytest -p no:cacheprovider --basetemp 'C:\Users\bhara\AppData\Local\Temp\opencode\nila-b1-final-review-20261112-01' -ra
```

```text
41 passed, 1 warning in 30.38s
PytestExitCode: 0
```

```text
ruff check src tests
All checks passed!
RuffExitCode: 0

mypy
Success: no issues found in 50 source files
MypyExitCode: 0
```

### Comparison to baseline

| Checkpoint | Result |
| --- | --- |
| Phase A original baseline | 35 passed, 1 warning in 29.66s |
| B1 before new contract tests | 35 passed, 1 warning in 26.77s |
| B1 final suite | 41 passed, 1 warning in 30.38s (this review) |

The original 35 tests are still present and unchanged. The six new tests are four execution-contract tests and two source-boundary tests.

### Independent claim probe

A review-only probe used two separate service instances and two threads against one disposable SQLite database. Simultaneous direct `ExecutionRepository.claim` calls produced one `ActionClaim` and one `DomainError`; the action remained `running` from the successful claim. The probe was not added to the repository.

## 8. Unresolved PostgreSQL and operational risks

These are intentional B1 boundaries, not defects in the SQLite implementation:

- There is no PostgreSQL adapter, driver, schema, RLS policy, or Supabase configuration.
- `Database.migrate()` still runs SQLite-specific Alembic DDL; a PostgreSQL deployment needs a separate migration history and deployment-time migration execution.
- `MemoryRepository` hardcodes the SQLite FTS5 search strategy; PostgreSQL requires a text-search strategy and Unicode/ranking validation.
- Row locking, conditional updates, and lost-commit reconciliation have not been tested against PostgreSQL.
- Global startup recovery has no worker lease or fencing and must not run unchanged in multiple workers.
- The in-memory busy-conversation set is process-local.
- Approval and lease expiration still use application wall-clock time.
- Owner columns, owner-scoped queries, RLS, cloud-persistence consent, and embedding consent are documented designs only.
- There is no import/cutover utility; existing local data must not be uploaded automatically.
- There is no exactly-once external-side-effect guarantee; unknown outcomes remain interrupted for review.
- Automatic migration at service startup remains in place for local SQLite.

## 9. Recommendation

**Technical verdict: accept the reviewed B1 snapshot as a SQLite-only persistence seam.** The refactor preserves the existing tests and HTTP/CLI behavior, isolates the intended SQLite implementation details, and correctly implements the current single-use approval and stale-completion rules.

**Process gate:** B1 is already in commit `dcb0171`, and the local `origin/main` tracking ref points to that commit. This review did not perform that commit or any push. Confirm that the commit and tracking-ref state are intentional, and decide separately whether a rollback or follow-up commit is required. This report does not recommend or perform a revert.

Before Phase B2, address the two medium review items or explicitly carry them into the B2/B3 plans:

1. Add a true concurrent claim test that actually overlaps database transactions.
2. Add attempt/relationship validation to completion, then extend it to a lease/attempt identity for PostgreSQL.

Do not begin PostgreSQL schema, Supabase connection, ownership/RLS, or data import work until Phase B1 is explicitly accepted.
