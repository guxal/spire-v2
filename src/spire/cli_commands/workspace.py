"""Read-only workspace observability command."""

from __future__ import annotations

from typing import Any

from .common import CommandContext


def status(ctx: CommandContext, _args) -> int:
    ctx.emit(ctx.api.workspace_status(), human=_human_status)
    return 0


def _human_status(payload: dict[str, Any]) -> str:
    return "\n".join(
        (
            f"Project root: {payload['project_root']}",
            f"Customer workspace root pattern: {payload['customer_root_pattern']}",
            f"Configured customer count: {payload['configured_customer_count']}",
            f"Execution store available: {payload['execution_store_available']}",
        )
    )
