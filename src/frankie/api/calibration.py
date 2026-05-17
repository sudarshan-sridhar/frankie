"""Workspace recalibration endpoint.

POST /api/calibrate_all runs the full physical recalibration pass: home
the arm, close the gripper, grab a snapshot, detect the 4 ArUco markers,
recompute the homography, persist it, and reload it onto app.state. The
background watcher in frankie.services.calibration_watcher invokes the
same flow when it sees marker drift, so the logic lives here in a
reusable async helper.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from fastapi import APIRouter, HTTPException, Request

from frankie.api.models import ApiError, CalibrateAllResponse
from frankie.vision.aruco import detect_markers
from frankie.vision.workspace import (
    Workspace,
    compute_workspace_from_detections,
    save_workspace,
)

if TYPE_CHECKING:
    from frankie.hardware.arm import Arm
    from frankie.vision.camera import Camera

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api")


class CalibrationFailureError(RuntimeError):
    """Raised when the recalibration pipeline cannot complete."""

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


async def run_full_recalibration(app_state) -> dict[int, tuple[float, float]]:
    """Run the complete recalibration flow and return marker pixel centers.

    Steps: home the arm, close the gripper, snapshot the camera, detect
    markers, compute homography, save to disk, swap the Workspace on
    app.state. Raises CalibrationFailureError for any missing prerequisite or
    detection shortfall.
    """
    cam: Camera | None = getattr(app_state, "camera", None)
    if cam is None:
        raise CalibrationFailureError("camera not configured", "no_camera")

    arm: Arm | None = getattr(app_state, "arm", None)
    if arm is None:
        raise CalibrationFailureError("arm not configured", "no_arm")

    try:
        await arm.home()
    except Exception as exc:
        log.exception("calibrate_all.home_failed")
        raise CalibrationFailureError(f"home failed: {exc}", "home_failed") from exc

    try:
        await arm.gripper_close()
    except Exception as exc:
        log.exception("calibrate_all.gripper_close_failed")
        raise CalibrationFailureError(
            f"gripper close failed: {exc}", "gripper_failed"
        ) from exc

    try:
        frame = await cam.snapshot()
    except TimeoutError as exc:
        raise CalibrationFailureError(f"camera timeout: {exc}", "camera_timeout") from exc

    detections = detect_markers(frame)
    detected_ids = sorted(d.id for d in detections)
    if len(detections) < 4:
        raise CalibrationFailureError(
            f"need 4 markers, detected {detected_ids}",
            "insufficient_markers",
        )

    try:
        cal = compute_workspace_from_detections(detections)
    except (ValueError, RuntimeError) as exc:
        raise CalibrationFailureError(str(exc), "homography_failed") from exc

    save_workspace(cal)
    app_state.workspace = Workspace(cal)

    log.info("calibrate_all.ok", markers=detected_ids)
    return cal.marker_pixel_centers


@router.post("/calibrate_all", response_model=CalibrateAllResponse)
async def calibrate_all(request: Request) -> CalibrateAllResponse:
    """Run the full recalibration flow synchronously."""
    try:
        centers = await run_full_recalibration(request.app.state)
    except CalibrationFailureError as exc:
        status = 503 if exc.code in ("no_camera", "no_arm") else 400
        if exc.code == "camera_timeout":
            status = 504
        raise HTTPException(
            status_code=status,
            detail=ApiError(error=str(exc), code=exc.code).model_dump(),
        ) from exc

    # Emit a one-shot recalibrated event so any /ws/state listener can
    # surface it (the watcher uses the same plumbing for auto-runs).
    events = getattr(request.app.state, "events", None)
    if events is not None:
        await events.publish({"event": "workspace.recalibrated", "markers": centers})

    return CalibrateAllResponse(status="ok", markers=centers)
