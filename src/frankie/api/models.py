"""Pydantic request and response models for the HTTP API."""

from __future__ import annotations

from pydantic import BaseModel, Field

from frankie.hardware.calibration import CalibrationData
from frankie.state import ArmState, RunMode
from frankie.vision.workspace import WorkspaceCalibration


class JogRequest(BaseModel):
    """POST /api/jog body."""

    joint: str
    angle_deg: float


class GripperSetRequest(BaseModel):
    """POST /api/gripper/set body."""

    ratio: float = Field(ge=0.0, le=1.0)


class MoveToPixelRequest(BaseModel):
    """POST /api/move_to_pixel body."""

    px: tuple[float, float]
    z_mm: float = 30.0


class MoveToWorldRequest(BaseModel):
    """POST /api/move_to_world body."""

    world: tuple[float, float, float]


class PickPlaceRequest(BaseModel):
    """POST /api/pick or /api/place body."""

    world_xy: tuple[float, float]
    approach_z_mm: float | None = None
    contact_z_mm: float | None = None


class VisionDescribeRequest(BaseModel):
    """POST /api/vision/describe body."""

    prompt: str


class VisionResponse(BaseModel):
    """POST /api/vision/describe response."""

    text: str


class StateResponse(BaseModel):
    """GET /api/state body."""

    mode: RunMode
    arm: ArmState
    # Forward-kinematics TCP position (mm) when kinematics are loaded. The
    # mobile app's Manual screen reads this for the live XYZ overlay.
    world_xyz_mm: tuple[float, float, float] | None = None


class CalibrationResponse(BaseModel):
    """GET /api/calibration body wrapper."""

    calibration: CalibrationData


class WorkspaceResponse(BaseModel):
    """GET /api/workspace body wrapper."""

    workspace: WorkspaceCalibration | None


class MoveResponse(BaseModel):
    """Returned from move_to_pixel / move_to_world."""

    mode: RunMode
    arm: ArmState
    target_world_mm: tuple[float, float, float]
    joint_angles_deg: dict[str, float]


class ApiError(BaseModel):
    """Uniform error payload."""

    error: str
    code: str


class CommandRequest(BaseModel):
    """POST /api/command body."""

    text: str
    session_id: str | None = None


class CommandResponse(BaseModel):
    """POST /api/command response: a ModeResponse plus session metadata."""

    spoken: str
    action_taken: str
    visual: str | None = None
    next_state: dict = {}
    session_id: str


class ModesResponse(BaseModel):
    """GET /api/modes body."""

    available: list[str]
    active: str | None


class VoiceResponse(BaseModel):
    """POST /api/voice response body."""

    transcript: str


class CalibrateAllResponse(BaseModel):
    """POST /api/calibrate_all response body."""

    status: str
    markers: dict[int, tuple[float, float]]


class ChatMessageModel(BaseModel):
    """One persisted chat message."""

    id: int
    robot_id: str
    session_id: str
    turn_index: int
    role: str
    content: str
    model_used: str | None = None
    action_taken: str | None = None
    created_at: str


class SessionSummaryModel(BaseModel):
    """Summary of a chat session for the sessions list."""

    session_id: str
    first_user_message: str | None
    last_update: str
    message_count: int


class SessionsListResponse(BaseModel):
    """GET /api/chat/sessions response."""

    sessions: list[SessionSummaryModel]


class SessionMessagesResponse(BaseModel):
    """GET /api/chat/{session_id} response."""

    session_id: str
    messages: list[ChatMessageModel]
