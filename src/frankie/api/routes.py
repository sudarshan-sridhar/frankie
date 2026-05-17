"""HTTP routes.

Phase 1 added /health (in main.py).
Phase 2 added /api/state, /api/jog, /api/gripper/{open,close,set},
/api/home, /api/estop, /api/clear_estop, /api/calibration.
Phase 3 adds /api/camera/snapshot, /api/move_to_pixel, /api/move_to_world,
/api/vision/describe, /api/workspace, /api/workspace/reload.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING

import cv2
import httpx
import structlog
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse

from frankie.api.models import (
    ApiError,
    CalibrationResponse,
    ChatMessageModel,
    CommandRequest,
    CommandResponse,
    GripperSetRequest,
    JogRequest,
    ModesResponse,
    MoveResponse,
    MoveToPixelRequest,
    MoveToWorldRequest,
    PickPlaceRequest,
    SessionMessagesResponse,
    SessionSummaryModel,
    SessionsListResponse,
    StateResponse,
    VisionDescribeRequest,
    VisionResponse,
    VoiceResponse,
    WorkspaceResponse,
)
from frankie.config import get_settings
from frankie.storage import chat as chat_store
from frankie.vision.workspace import draw_grid_overlay
from frankie.hardware.arm import (
    DEFAULT_APPROACH_Z_MM,
    DEFAULT_PICK_Z_MM,
    DEFAULT_PLACE_Z_MM,
)
from frankie.hardware.calibration import (
    CalibrationData,
    load_calibration,
    save_calibration,
)
from frankie.hardware.kinematics import DHParameters, Kinematics
from frankie.modes.base import Mode, ModeResponse
from frankie.safety import SafetyMonitor
from frankie.vision.workspace import (
    Workspace,
    load_workspace,
)

ROBOT_ID = "frankie"

if TYPE_CHECKING:
    from frankie.hardware.arm import Arm
    from frankie.state import RunMode
    from frankie.vision.camera import Camera
    from frankie.vision.claude_vision import ClaudeVision

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api")


# ---------------------------------------------------------------- helpers

def _arm(request: Request) -> Arm:
    return request.app.state.arm  # type: ignore[no-any-return]


def _mode(request: Request) -> RunMode:
    return request.app.state.mode  # type: ignore[no-any-return]


def _calibration(request: Request) -> CalibrationData:
    return request.app.state.calibration  # type: ignore[no-any-return]


def _camera(request: Request) -> Camera | None:
    return getattr(request.app.state, "camera", None)


def _workspace(request: Request) -> Workspace | None:
    return getattr(request.app.state, "workspace", None)


def _kinematics(request: Request) -> Kinematics | None:
    return getattr(request.app.state, "kinematics", None)


def _claude(request: Request) -> ClaudeVision | None:
    return getattr(request.app.state, "claude", None)


def _modes(request: Request) -> dict[str, Mode]:
    return getattr(request.app.state, "modes", {})


def _active_mode(request: Request) -> Mode | None:
    name = getattr(request.app.state, "active_mode_name", None)
    if name is None:
        return None
    return _modes(request).get(name)


def _apply_calibration(request: Request, cal: CalibrationData) -> None:
    request.app.state.calibration = cal
    request.app.state.safety = SafetyMonitor.from_calibration(cal)
    _arm(request).reload_calibration(cal)


# ---------------------------------------------------------------- state / motion

@router.get("/state", response_model=StateResponse)
async def get_state(request: Request) -> StateResponse:
    arm_state = _arm(request).get_state()
    ik = _kinematics(request)
    xyz: tuple[float, float, float] | None = None
    if ik is not None:
        try:
            angles = {name: j.angle_deg for name, j in arm_state.joints.items()}
            xyz = ik.forward(angles)
        except Exception:
            xyz = None
    return StateResponse(mode=_mode(request), arm=arm_state, world_xyz_mm=xyz)


@router.post("/jog")
async def jog(request: Request, body: JogRequest) -> StateResponse:
    try:
        await _arm(request).jog_joint(body.joint, body.angle_deg)
    except (ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=400,
            detail=ApiError(error=str(exc), code="jog").model_dump(),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail=ApiError(error=str(exc), code="estop").model_dump(),
        ) from exc
    return StateResponse(mode=_mode(request), arm=_arm(request).get_state())


@router.post("/gripper/open")
async def gripper_open(request: Request) -> StateResponse:
    await _arm(request).gripper_open()
    return StateResponse(mode=_mode(request), arm=_arm(request).get_state())


@router.post("/gripper/close")
async def gripper_close(request: Request) -> StateResponse:
    await _arm(request).gripper_close()
    return StateResponse(mode=_mode(request), arm=_arm(request).get_state())


@router.post("/gripper/set")
async def gripper_set(request: Request, body: GripperSetRequest) -> StateResponse:
    await _arm(request).gripper_set(body.ratio)
    return StateResponse(mode=_mode(request), arm=_arm(request).get_state())


@router.post("/home")
async def home(request: Request) -> StateResponse:
    try:
        await _arm(request).home()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail=ApiError(error=str(exc), code="estop").model_dump(),
        ) from exc
    return StateResponse(mode=_mode(request), arm=_arm(request).get_state())


@router.post("/estop")
async def estop(request: Request) -> StateResponse:
    await _arm(request).emergency_stop()
    return StateResponse(mode=_mode(request), arm=_arm(request).get_state())


@router.post("/clear_estop")
async def clear_estop(request: Request) -> StateResponse:
    _arm(request).clear_estop()
    return StateResponse(mode=_mode(request), arm=_arm(request).get_state())


# ---------------------------------------------------------------- calibration

@router.get("/calibration", response_model=CalibrationResponse)
async def get_calibration(request: Request) -> CalibrationResponse:
    return CalibrationResponse(calibration=_calibration(request))


@router.post("/calibration", response_model=CalibrationResponse)
async def post_calibration(request: Request, body: CalibrationData) -> CalibrationResponse:
    save_calibration(body)
    _apply_calibration(request, body)
    log.info("calibration.saved", channels=len(body.channels))
    return CalibrationResponse(calibration=body)


@router.post("/calibration/reload", response_model=CalibrationResponse)
async def reload_calibration(request: Request) -> CalibrationResponse:
    cal = load_calibration()
    _apply_calibration(request, cal)
    log.info("calibration.reloaded")
    return CalibrationResponse(calibration=cal)


@router.get("/workspace", response_model=WorkspaceResponse)
async def get_workspace(request: Request) -> WorkspaceResponse:
    ws = _workspace(request)
    return WorkspaceResponse(workspace=ws.calibration if ws else None)


@router.post("/workspace/reload", response_model=WorkspaceResponse)
async def reload_workspace(request: Request) -> WorkspaceResponse:
    cal = load_workspace()
    if cal is None:
        request.app.state.workspace = None
        return WorkspaceResponse(workspace=None)
    request.app.state.workspace = Workspace(cal)
    log.info("workspace.reloaded")
    return WorkspaceResponse(workspace=cal)


@router.post("/kinematics/reload")
async def reload_kinematics(request: Request) -> dict[str, object]:
    """Re-read data/calibration/arm_dh.json and rebuild the IK chain."""
    try:
        dh = DHParameters.load()
    except FileNotFoundError as exc:
        request.app.state.kinematics = None
        raise HTTPException(
            status_code=404,
            detail=ApiError(error=str(exc), code="no_dh").model_dump(),
        ) from exc
    request.app.state.kinematics = Kinematics(dh)
    log.info("kinematics.reloaded")
    return {
        "ok": True,
        "dh": {
            "L0_base_to_shoulder": dh.L0_base_to_shoulder,
            "L1_shoulder_to_elbow": dh.L1_shoulder_to_elbow,
            "L2_elbow_to_wrist": dh.L2_elbow_to_wrist,
            "L3_wrist_to_gripper": dh.L3_wrist_to_gripper,
        },
    }


# ---------------------------------------------------------------- camera

@router.get("/camera/snapshot")
async def camera_snapshot(request: Request) -> Response:
    cam = _camera(request)
    if cam is None:
        raise HTTPException(
            status_code=503,
            detail=ApiError(error="camera not configured", code="no_camera").model_dump(),
        )
    try:
        frame = await cam.snapshot()
    except TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail=ApiError(error=str(exc), code="camera_timeout").model_dump(),
        ) from exc
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        raise HTTPException(status_code=500, detail="encode failed")
    return Response(content=buf.tobytes(), media_type="image/jpeg")


# HTTP multipart MJPEG stream. RN <Image> and <WebView> can both render
# this directly, which is awkward over a raw WebSocket on native.
_STREAM_BOUNDARY = "frame"
_STREAM_FPS = 15.0
_STREAM_JPEG_QUALITY = 70


@router.get("/camera/stream")
async def camera_stream(request: Request) -> StreamingResponse:
    cam = _camera(request)
    if cam is None:
        raise HTTPException(
            status_code=503,
            detail=ApiError(error="camera not configured", code="no_camera").model_dump(),
        )

    async def generator():
        interval = 1.0 / _STREAM_FPS
        while True:
            if await request.is_disconnected():
                break
            frame = await cam.latest_frame()
            if frame is not None:
                workspace = _workspace(request)
                if workspace is not None:
                    frame = draw_grid_overlay(frame, workspace)
                ok, buf = cv2.imencode(
                    ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), _STREAM_JPEG_QUALITY]
                )
                if ok:
                    chunk = buf.tobytes()
                    header = (
                        f"--{_STREAM_BOUNDARY}\r\n"
                        f"Content-Type: image/jpeg\r\n"
                        f"Content-Length: {len(chunk)}\r\n\r\n"
                    ).encode("ascii")
                    yield header + chunk + b"\r\n"
            await asyncio.sleep(interval)

    return StreamingResponse(
        generator(),
        media_type=f"multipart/x-mixed-replace; boundary={_STREAM_BOUNDARY}",
    )


# ---------------------------------------------------------------- move-to-target

@router.post("/move_to_world", response_model=MoveResponse)
async def move_to_world(request: Request, body: MoveToWorldRequest) -> MoveResponse:
    ik = _kinematics(request)
    if ik is None:
        raise HTTPException(
            status_code=503,
            detail=ApiError(error="kinematics not configured", code="no_ik").model_dump(),
        )
    target: tuple[float, float, float] = (body.world[0], body.world[1], body.world[2])
    if not ik.is_reachable(target):
        raise HTTPException(
            status_code=400,
            detail=ApiError(error=f"unreachable {target}", code="unreachable").model_dump(),
        )
    arm = _arm(request)
    current = {name: joint.angle_deg for name, joint in arm.get_state().joints.items()}
    angles = ik.inverse(target, initial_angles_deg=current)
    for joint in ("base", "shoulder", "elbow", "wrist"):
        try:
            await arm.jog_joint(joint, angles[joint])
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(
                status_code=400,
                detail=ApiError(error=str(exc), code="ik_step").model_dump(),
            ) from exc
    return MoveResponse(
        mode=_mode(request),
        arm=arm.get_state(),
        target_world_mm=target,
        joint_angles_deg=angles,
    )


@router.post("/pick")
async def pick(request: Request, body: PickPlaceRequest) -> StateResponse:
    """Open → hover above XY → descend → close → lift. Uses validated defaults."""
    ik = _kinematics(request)
    if ik is None:
        raise HTTPException(
            status_code=503,
            detail=ApiError(error="kinematics not configured", code="no_ik").model_dump(),
        )
    arm = _arm(request)
    try:
        await arm.pick_at(
            body.world_xy,
            ik,
            approach_z_mm=body.approach_z_mm or DEFAULT_APPROACH_Z_MM,
            pick_z_mm=body.contact_z_mm or DEFAULT_PICK_Z_MM,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ApiError(error=str(exc), code="unreachable").model_dump(),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail=ApiError(error=str(exc), code="estop").model_dump(),
        ) from exc
    return StateResponse(mode=_mode(request), arm=arm.get_state())


@router.post("/place")
async def place(request: Request, body: PickPlaceRequest) -> StateResponse:
    """Hover above XY → descend → open → lift. Mirror of /pick for the drop phase."""
    ik = _kinematics(request)
    if ik is None:
        raise HTTPException(
            status_code=503,
            detail=ApiError(error="kinematics not configured", code="no_ik").model_dump(),
        )
    arm = _arm(request)
    try:
        await arm.place_at(
            body.world_xy,
            ik,
            approach_z_mm=body.approach_z_mm or DEFAULT_APPROACH_Z_MM,
            place_z_mm=body.contact_z_mm or DEFAULT_PLACE_Z_MM,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ApiError(error=str(exc), code="unreachable").model_dump(),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail=ApiError(error=str(exc), code="estop").model_dump(),
        ) from exc
    return StateResponse(mode=_mode(request), arm=arm.get_state())


@router.post("/move_to_pixel", response_model=MoveResponse)
async def move_to_pixel(request: Request, body: MoveToPixelRequest) -> MoveResponse:
    ws = _workspace(request)
    if ws is None:
        raise HTTPException(
            status_code=503,
            detail=ApiError(error="workspace not calibrated", code="no_workspace").model_dump(),
        )
    px: tuple[float, float] = (body.px[0], body.px[1])
    world_xy = ws.pixel_to_world(px)
    if not ws.is_in_reachable_region(world_xy):
        raise HTTPException(
            status_code=400,
            detail=ApiError(error=f"pixel maps outside reachable region: {world_xy}", code="out_of_region").model_dump(),
        )
    world = (world_xy[0], world_xy[1], body.z_mm)
    return await move_to_world(request, MoveToWorldRequest(world=world))


# ---------------------------------------------------------------- vision

@router.post("/vision/describe", response_model=VisionResponse)
async def vision_describe(request: Request, body: VisionDescribeRequest) -> VisionResponse:
    cam = _camera(request)
    claude = _claude(request)
    if cam is None or claude is None:
        raise HTTPException(
            status_code=503,
            detail=ApiError(
                error="camera or vision client not configured",
                code="no_vision",
            ).model_dump(),
        )
    try:
        frame = await cam.snapshot()
    except TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail=ApiError(error=str(exc), code="camera_timeout").model_dump(),
        ) from exc
    text = await claude.describe(frame, body.prompt)
    return VisionResponse(text=text)


# ---------------------------------------------------------------- modes + command

@router.get("/modes", response_model=ModesResponse)
async def get_modes(request: Request) -> ModesResponse:
    """List available modes and which one (if any) is active."""
    return ModesResponse(
        available=sorted(_modes(request).keys()),
        active=getattr(request.app.state, "active_mode_name", None),
    )


@router.post("/mode/{name}", response_model=ModesResponse)
async def set_mode(request: Request, name: str) -> ModesResponse:
    """Activate a mode by name. Calls start() on the new mode and stop() on the old one."""
    modes = _modes(request)
    if name not in modes:
        raise HTTPException(
            status_code=404,
            detail=ApiError(
                error=f"mode {name!r} not available; have {sorted(modes.keys())}",
                code="no_mode",
            ).model_dump(),
        )
    current_name = getattr(request.app.state, "active_mode_name", None)
    if current_name and current_name != name:
        current = modes.get(current_name)
        if current is not None:
            await current.stop()
    await modes[name].start()
    request.app.state.active_mode_name = name
    log.info("mode.activated", name=name, previous=current_name)
    return ModesResponse(available=sorted(modes.keys()), active=name)


# Intent-based auto mode switch so the user can stay in free mode in the
# chat surface but still trigger toolship / defect by speaking the request
# in natural language ("give me M6", "find the defective part"). The mode
# is switched, the command is dispatched, and we revert to free afterward
# so the next conversational turn keeps flowing.
import re as _re

# Toolship triggers: any phrasing that asks for a tool by Mxx code.
_TOOLSHIP_INTENT = _re.compile(
    r"\b(give|hand|pass|bring|need|get|fetch|grab)\s+(me\s+)?(an?\s+|the\s+)?m\d{1,2}\b",
    _re.IGNORECASE,
)
# Defect triggers: covers both teach phrasings ("this cube is defective",
# "teach defect", "the blue one is bad") and inspect phrasings ("find the
# defective part", "which is defective"). The mode itself disambiguates
# between teach (single object on bench) and inspect (multiple objects).
_DEFECT_INTENT = _re.compile(
    r"\b("
    r"teach\s+defect(?:ive)?"
    r"|(?:this|that|the)\s+\w+\s+(?:is|has)\s+(?:defective|broken|scratched|damaged|a\s+defect)"
    r"|find\s+(?:the\s+)?(?:defective|defect|bad\s+one)"
    r"|defective\s+part"
    r"|inspect\s+(?:the\s+)?part"
    r"|which\s+(?:one\s+)?is\s+defective"
    r"|is\s+defective"
    r")\b",
    _re.IGNORECASE,
)


def _resolve_target_mode(text: str) -> str | None:
    """Return the mode the operator's command implies, or None to stay put."""
    if _TOOLSHIP_INTENT.search(text):
        return "toolship"
    if _DEFECT_INTENT.search(text):
        return "defect"
    return None


@router.post("/command", response_model=CommandResponse)
async def post_command(request: Request, body: CommandRequest) -> CommandResponse:
    """Dispatch a free-text command to the active mode and persist the turn.

    If the command text matches a non-free-mode intent (e.g. "give me M6"),
    the active mode is auto-switched to the matching mode for this single
    dispatch and reverted to free afterward, so the chat surface can drive
    every mode without an explicit /api/mode call.
    """
    modes = _modes(request)
    active_name = getattr(request.app.state, "active_mode_name", None)
    target_name = _resolve_target_mode(body.text)
    auto_switched = False
    if target_name and target_name in modes and target_name != active_name:
        prev = modes.get(active_name) if active_name else None
        if prev is not None:
            try:
                await prev.stop()
            except Exception:
                log.exception("mode.stop_failed_during_autoswitch", name=active_name)
        try:
            await modes[target_name].start()
            request.app.state.active_mode_name = target_name
            auto_switched = True
            log.info("mode.auto_switched", to=target_name, from_=active_name)
        except Exception:
            log.exception("mode.start_failed_during_autoswitch", name=target_name)

    mode = _active_mode(request)
    if mode is None:
        raise HTTPException(
            status_code=400,
            detail=ApiError(
                error="no mode active. POST /api/mode/<name> first.",
                code="no_active_mode",
            ).model_dump(),
        )

    session_id = body.session_id or str(uuid.uuid4())

    try:
        result = await mode.handle_command(body.text, context={})
    except NotImplementedError as exc:
        raise HTTPException(
            status_code=501,
            detail=ApiError(
                error=f"{mode.name} mode is not implemented yet",
                code="not_implemented",
            ).model_dump(),
        ) from exc

    # If we auto-switched to fulfill a one-shot intent, revert to free so the
    # chat surface keeps flowing conversationally.
    if auto_switched and "free" in modes and mode.name != "free":
        try:
            await mode.stop()
            await modes["free"].start()
            request.app.state.active_mode_name = "free"
        except Exception:
            log.exception("mode.revert_failed", name=mode.name)

    # Mask the actual model behind a single "granite" badge so the app surface
    # stays consistent for the demo. Claude is the silent fallback / vision
    # accuracy backstop; the screen should only ever read "granite".
    next_state = dict(result.next_state) if result.next_state else {}
    if "model_used" in next_state:
        next_state["model_used"] = "granite"

    # Persist both turns. Failures here must not break the response.
    try:
        await chat_store.record_message(
            robot_id=ROBOT_ID,
            session_id=session_id,
            role="user",
            content=body.text,
        )
        await chat_store.record_message(
            robot_id=ROBOT_ID,
            session_id=session_id,
            role="assistant",
            content=result.spoken,
            model_used=mode.name,
            action_taken=result.action_taken,
        )
    except Exception:
        log.exception("chat.record_failed", session_id=session_id)

    return CommandResponse(
        spoken=result.spoken,
        action_taken=result.action_taken,
        visual=result.visual,
        next_state=next_state,
        session_id=session_id,
    )


# ---------------------------------------------------------------- chat history

@router.get("/chat/sessions", response_model=SessionsListResponse)
async def get_chat_sessions() -> SessionsListResponse:
    """List all chat sessions for the demo robot."""
    summaries = await chat_store.list_sessions(ROBOT_ID)
    return SessionsListResponse(
        sessions=[SessionSummaryModel(**s.model_dump()) for s in summaries]
    )


@router.get("/chat/{session_id}", response_model=SessionMessagesResponse)
async def get_chat_session(session_id: str) -> SessionMessagesResponse:
    """Return all messages from a single session in turn order."""
    messages = await chat_store.get_session(ROBOT_ID, session_id)
    return SessionMessagesResponse(
        session_id=session_id,
        messages=[ChatMessageModel(**m.model_dump()) for m in messages],
    )


# ---------------------------------------------------------------- voice (Whisper)

_WHISPER_URL = "https://api.openai.com/v1/audio/transcriptions"
_WHISPER_MODEL = "whisper-1"
_WHISPER_RETRY_STATUSES = {429, 500, 502, 503, 504}
_WHISPER_MAX_ATTEMPTS = 3
_WHISPER_BASE_BACKOFF_S = 0.5
_WHISPER_TIMEOUT_S = 60.0


@router.post("/voice", response_model=VoiceResponse)
async def post_voice(
    request: Request,
    audio: UploadFile = File(...),  # noqa: B008 — FastAPI dependency marker
) -> VoiceResponse:
    """Forward an audio upload to OpenAI Whisper and return the transcript."""
    settings = get_settings()
    api_key = settings.openai_api_key
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail=ApiError(
                error="Whisper not configured (OPENAI_API_KEY empty)",
                code="no_whisper",
            ).model_dump(),
        )

    data = await audio.read()
    if not data:
        raise HTTPException(
            status_code=400,
            detail=ApiError(error="empty audio upload", code="empty_audio").model_dump(),
        )

    filename = audio.filename or "audio.m4a"
    content_type = audio.content_type or "audio/m4a"
    files = {"file": (filename, data, content_type)}
    form = {"model": _WHISPER_MODEL}
    headers = {"Authorization": f"Bearer {api_key}"}

    last_status: int | None = None
    last_text: str = ""
    async with httpx.AsyncClient(timeout=_WHISPER_TIMEOUT_S) as client:
        for attempt in range(1, _WHISPER_MAX_ATTEMPTS + 1):
            try:
                resp = await client.post(
                    _WHISPER_URL, headers=headers, data=form, files=files
                )
            except httpx.HTTPError as exc:
                log.warning("whisper.http_error", attempt=attempt, error=str(exc))
                last_text = str(exc)
                await asyncio.sleep(_WHISPER_BASE_BACKOFF_S * (2 ** (attempt - 1)))
                continue

            if resp.status_code in _WHISPER_RETRY_STATUSES:
                last_status = resp.status_code
                last_text = resp.text[:300]
                log.warning(
                    "whisper.retry", attempt=attempt, status=resp.status_code
                )
                ra = resp.headers.get("Retry-After")
                delay = (
                    float(ra)
                    if ra and ra.replace(".", "", 1).isdigit()
                    else _WHISPER_BASE_BACKOFF_S * (2 ** (attempt - 1))
                )
                await asyncio.sleep(delay)
                continue

            if resp.status_code >= 400:
                raise HTTPException(
                    status_code=502,
                    detail=ApiError(
                        error=f"whisper {resp.status_code}: {resp.text[:300]}",
                        code="whisper_failed",
                    ).model_dump(),
                )

            payload = resp.json()
            transcript = payload.get("text", "")
            return VoiceResponse(transcript=transcript)

    raise HTTPException(
        status_code=502,
        detail=ApiError(
            error=f"whisper unavailable after {_WHISPER_MAX_ATTEMPTS} attempts "
            f"(last: {last_status} {last_text})",
            code="whisper_unavailable",
        ).model_dump(),
    )
