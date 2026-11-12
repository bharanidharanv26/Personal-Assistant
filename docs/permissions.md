# Consent, approval and data boundaries

## Local API access

`nila serve` binds only to `127.0.0.1`. Every application endpoint, including health, requires a bearer token. The token is randomly generated and stored under the `NILA-AI` service in the OS credential store. The CLI reads it locally. Tokens and provider keys can also come from environment settings; they are not stored in SQLite.

The API accepts only localhost/loopback host headers. Browser CORS access and interactive API documentation are not enabled. Anyone who can read your local token is an authorized API client; this is a single-user application rather than a multi-user security boundary.

## Approval

An action preview includes its task ID, sequence position, registered tool, exact arguments, and SHA-256 digest. The digest includes task revision and tool version. It detects changes between preview, approval and execution; it is not a digital signature protecting against a user who controls the database and process.

The user approves the digest of the preview. A valid approval must be unexpired, unconsumed, and match the current action. The executor rechecks these conditions and the task's state atomically before running a tool. Modified actions, unknown tools, cancelled tasks, and out-of-order actions cannot execute.

- **Deny** rejects a proposed action and cancels remaining task steps.
- **Revoke** removes an unconsumed approval and cancels remaining task steps.
- **Cancel task** blocks pending steps; an already-running step may still complete.
- **Expire** blocks execution until the exact current preview is explicitly approved again.
- **Consume** occurs before execution and blocks replay even when execution fails.

The LLM sees no API token and has no approval endpoint or approval tool. Prompt text, saved memory, observation notes and model output cannot directly change permission records. This version exposes only a typed `dry_run` tool.

## Observation consent

The only supported scope is `manual_observation`. A consent record has an expiry and can be revoked. Inserting a note checks the scope, expiry and revocation in the same serialized write transaction as the insert. Consent does not authorize other observation types or computer actions.

Consent revocation affects new collection. Existing notes can be inspected and explicitly deleted. No sensors or background collectors run in v0.1.

## Personal data

Memories default to local-only retrieval. `--allow-remote` is required to include a memory in a hosted prompt. The current message/objective and eligible same-provider history are also sent in hosted mode. A user can of course choose to include private information directly in a message; the memory sharing flag does not filter user-authored text.

Observations and feedback are not included in prompts. They are not automatically promoted to memory or exported as training data. Secrets belong in the OS credential store, not memory entries or task arguments.

The SQLite database is not encrypted by NILA. Operating-system account permissions and device encryption provide the local storage boundary. Removing a memory deletes its active record and FTS entry and excludes dependent future context; it does not erase historical transcript text, old exports, backups, SQLite free pages, or already-sent provider data. Audit records contain metadata and are not tamper-proof.

## Future adapter requirements

Live browser/desktop adapters must declare their precise effects and targets, validate parameters at execution, participate in approval hashing/versioning, support time bounds, and report partial/unknown outcomes honestly. Real-world retry rules and browser state/profile isolation must be designed before enabling those adapters.
