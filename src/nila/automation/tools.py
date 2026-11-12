import hashlib
import json
from typing import Any

from nila.core.schemas import DryRunArguments


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


class ToolRegistry:
    def validate(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if tool != "dry_run":
            raise ValueError("Tool is not registered")
        return DryRunArguments.model_validate(arguments).model_dump()

    async def execute(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        validated = self.validate(tool, arguments)
        return {
            "simulated": True,
            "description": validated["description"],
            "message": "Dry run completed. No browser, computer, or external action was performed.",
        }
