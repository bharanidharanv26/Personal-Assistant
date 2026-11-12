# Local API reference

Base URL: `http://127.0.0.1:8765`. All endpoints require `Authorization: Bearer <local-token>`. The CLI handles this header automatically. JSON request objects reject unknown fields. List endpoints accept `limit` (default 100, maximum 500); memory search defaults to 5 with a maximum of 20.

| Method | Path | Request / purpose |
| --- | --- | --- |
| GET | `/health` | Version, provider, dry-run mode and step limit |
| POST | `/chat` | `{message, conversation_id?}` |
| GET | `/conversations/{id}/messages` | Persisted conversation messages |
| POST | `/memories` | `{content, kind?: "fact" or "preference", allow_remote?: false}` |
| GET | `/memories` | List memories |
| GET | `/memories/search?q=...` | Literal keyword retrieval |
| GET | `/memories/export` | Export all memories as JSON |
| PUT | `/memories/{id}` | Replace content, kind and sharing flag |
| DELETE | `/memories/{id}` | Delete the memory and index entry |
| POST | `/tasks` | `{objective}`; one bounded planning request |
| GET | `/tasks` | List tasks with their action previews |
| GET | `/tasks/{id}` | Task state, actions and outcomes |
| POST | `/tasks/{id}/cancel` | Cancel pending work |
| POST | `/tasks/{id}/run` | Execute approved remaining dry-run steps |
| GET | `/actions/{id}` | Exact action preview and digest |
| POST | `/actions/{id}/approve` | `{digest}` from the reviewed preview |
| POST | `/actions/{id}/deny` | Deny a proposed action |
| POST | `/actions/{id}/revoke` | Revoke an unconsumed approval |
| POST | `/actions/{id}/execute` | Execute one approved step in sequence |
| POST | `/consents` | `{scope?: "manual_observation", lifetime_seconds?: 3600}` |
| GET | `/consents` | List consent records, including expired/revoked records |
| POST | `/consents/{id}/revoke` | Revoke observation consent |
| POST | `/observations` | `{consent_id, content}` |
| GET | `/observations` | List manual observations |
| DELETE | `/observations/{id}` | Delete a stored observation |
| POST | `/feedback` | `{target_type, target_id, rating, correction?}` |
| GET | `/evaluation` | Descriptive outcome and feedback counts |
| GET | `/audit` | Identifier/status-only audit events |

Feedback targets are `message`, `task`, or `action`. Ratings are exactly `-1` or `1`. Message feedback targets an assistant reply; task/action feedback requires a terminal outcome. A repeat rating updates that target's current feedback rather than incrementing a counter indefinitely.

Times are Unix seconds in UTC. Creation endpoints return 201; successful deletion, denial and revocation of actions return 204. Domain errors use `{detail, resource_id}`. Validation errors return 422; missing authentication 401; invalid consent 403; unknown records 404; invalid state or stale/expired approval 409; provider/tool failures 502; tool timeout 504.

Client timeouts and transport failures do not prove that a request was never processed. Inspect persisted task/action state before retrying. Approval consumption blocks an action from executing twice. Creating a new task or sending a new chat message is a new request; these creation endpoints do not provide general idempotency keys in v0.1.
