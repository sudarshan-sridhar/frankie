"""WebSocket endpoints.

/ws/state pushes ArmState at 5Hz. /ws/camera pushes MJPEG frames as
binary WebSocket messages at ~15Hz so the frontend can render a live
preview without burning the Pi on full-resolution decoding.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import cv2
import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from frankie.vision.workspace import draw_grid_overlay

if TYPE_CHECKING:
    from frankie.hardware.arm import Arm
    from frankie.vision.camera import Camera
    from frankie.vision.workspace import Workspace

log = structlog.get_logger(__name__)
router = APIRouter()


STATE_PUSH_INTERVAL_S: float = 0.2
CAMERA_PUSH_INTERVAL_S: float = 1.0 / 15.0
CAMERA_JPEG_QUALITY: int = 70


@router.websocket("/ws/state")
async def ws_state(websocket: WebSocket) -> None:
    """Stream ArmState every 200ms plus any pending app events."""
    await websocket.accept()
    arm: Arm = websocket.app.state.arm
    mode = websocket.app.state.mode
    events = getattr(websocket.app.state, "events", None)
    queue = await events.subscribe() if events is not None else None
    try:
        while True:
            payload: dict[str, object] = {
                "mode": mode,
                "arm": arm.get_state().model_dump(),
            }
            # Drain any pending events into this frame so subscribers
            # see them within at most STATE_PUSH_INTERVAL_S of publish.
            if queue is not None:
                drained: list[dict[str, object]] = []
                while True:
                    try:
                        drained.append(queue.get_nowait())
                    except asyncio.QueueEmpty:
                        break
                if drained:
                    payload["events"] = drained
            await websocket.send_json(payload)
            await asyncio.sleep(STATE_PUSH_INTERVAL_S)
    except WebSocketDisconnect:
        log.debug("ws_state.disconnect")
    finally:
        if events is not None and queue is not None:
            await events.unsubscribe(queue)


@router.websocket("/ws/camera")
async def ws_camera(websocket: WebSocket) -> None:
    """Stream JPEG frames as binary messages at ~15Hz."""
    await websocket.accept()
    cam: Camera | None = getattr(websocket.app.state, "camera", None)
    if cam is None:
        await websocket.close(code=1011, reason="camera not configured")
        return
    try:
        while True:
            frame = await cam.latest_frame()
            if frame is not None:
                workspace: Workspace | None = getattr(websocket.app.state, "workspace", None)
                if workspace is not None:
                    frame = draw_grid_overlay(frame, workspace)
                ok, buf = cv2.imencode(
                    ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), CAMERA_JPEG_QUALITY]
                )
                if ok:
                    await websocket.send_bytes(buf.tobytes())
            await asyncio.sleep(CAMERA_PUSH_INTERVAL_S)
    except WebSocketDisconnect:
        log.debug("ws_camera.disconnect")
