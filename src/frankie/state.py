"""Shared in-process state types.

ArmState is the snapshot streamed over the /ws/state WebSocket and returned
from /api/state. Higher-level modules read and update this via the AppState
container held on the FastAPI app.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RunMode = Literal["hardware", "simulator"]


class JointState(BaseModel):
    """Last commanded position for a single joint."""

    name: str
    angle_deg: float
    pulse_us: int


class ArmState(BaseModel):
    """Current arm pose and gripper status."""

    mode: RunMode
    joints: dict[str, JointState] = Field(default_factory=dict)
    gripper_ratio: float = 0.0
    estopped: bool = False
    last_error: str | None = None


class AppState(BaseModel):
    """Top-level app state held on FastAPI.app.state."""

    mode: RunMode
    arm: ArmState

    model_config = {"arbitrary_types_allowed": True}
