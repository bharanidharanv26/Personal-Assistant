import hashlib
import json
from typing import Any


def action_digest(
    task_id: str, revision: int, position: int, tool: str, arguments: dict[str, Any]
) -> str:
    payload = {
        "task_id": task_id, "revision": revision, "position": position,
        "tool": tool, "tool_version": 1, "arguments": arguments,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
