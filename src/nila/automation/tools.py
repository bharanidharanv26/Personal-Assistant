from typing import Any

from nila.core.integrity import action_digest
from nila.core.schemas import DryRunArguments

__all__ = ["ToolRegistry", "action_digest"]


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
