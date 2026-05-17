"""Mode protocol and shared response shape.

Each mode (defect, toolship, chess) implements start/stop/handle_command.
The API layer dispatches incoming text commands to the active mode and
returns the ModeResponse to the frontend.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


class ModeResponse(BaseModel):
    """Returned from every Mode.handle_command call."""

    spoken: str
    action_taken: str
    visual: str | None = None
    next_state: dict[str, Any] = {}


@runtime_checkable
class Mode(Protocol):
    """Common interface for user-facing modes."""

    name: str

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def handle_command(
        self, command: str, context: dict[str, Any]
    ) -> ModeResponse: ...
