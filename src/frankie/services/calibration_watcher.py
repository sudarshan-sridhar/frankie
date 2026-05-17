"""Background watcher that auto-triggers workspace recalibration on drift.

Every 2 seconds it grabs the latest camera frame, detects ArUco markers,
and compares each marker's pixel center to the value persisted in the
WorkspaceCalibration. If any marker drifts more than DRIFT_THRESHOLD_PX
for STALE_PERSIST_S consecutive seconds, the watcher re-runs the same
recalibration flow as POST /api/calibrate_all and emits stale /
recalibrated events on the app's event broker. Partial or missing
detections never trigger a re-run; they just log ``recalibrate.deferred``.
"""

from __future__ import annotations

import asyncio
import math
import time
from typing import TYPE_CHECKING

import structlog

from frankie.api.calibration import CalibrationFailure, run_full_recalibration
from frankie.vision.aruco import detect_markers

if TYPE_CHECKING:
    from fastapi import FastAPI

log = structlog.get_logger(__name__)


CHECK_INTERVAL_S: float = 2.0
DRIFT_THRESHOLD_PX: float = 15.0
STALE_PERSIST_S: float = 3.0


class CalibrationWatcher:
    """Async task that detects marker drift and auto-recalibrates."""

    def __init__(self, app: FastAPI) -> None:
        self._app = app
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        # When did the workspace first start looking stale this run?
        self._stale_since: float | None = None
        # When are we in cool-down after a successful auto-recalibration?
        self._recal_cooldown_until: float = 0.0

    def start(self) -> None:
        """Spawn the background loop."""
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="calibration-watcher")

    async def stop(self) -> None:
        """Signal stop and await the loop exit."""
        self._stop.set()
        task = self._task
        if task is not None:
            try:
                await asyncio.wait_for(task, timeout=5.0)
            except (TimeoutError, asyncio.CancelledError):
                task.cancel()

    async def _run(self) -> None:
        log.info("calibration_watcher.started")
        try:
            while not self._stop.is_set():
                try:
                    await self._tick()
                except Exception:
                    log.exception("calibration_watcher.tick_failed")
                try:
                    await asyncio.wait_for(
                        self._stop.wait(), timeout=CHECK_INTERVAL_S
                    )
                except TimeoutError:
                    pass
        finally:
            log.info("calibration_watcher.stopped")

    async def _tick(self) -> None:
        state = self._app.state
        workspace = getattr(state, "workspace", None)
        camera = getattr(state, "camera", None)
        if workspace is None or camera is None:
            return
        if time.monotonic() < self._recal_cooldown_until:
            return

        calibrated_centers = workspace.calibration.marker_pixel_centers
        if not calibrated_centers:
            # Older calibrations may not have stored pixel centers; nothing
            # to compare against until a fresh /api/calibrate_all runs.
            return

        frame = await camera.latest_frame()
        if frame is None:
            return

        detections = detect_markers(frame)
        detected_by_id = {d.id: d.center_px for d in detections}

        expected_ids = set(calibrated_centers.keys())
        if not expected_ids.issubset(detected_by_id.keys()):
            log.debug(
                "recalibrate.deferred",
                reason="markers_missing",
                detected=sorted(detected_by_id.keys()),
                expected=sorted(expected_ids),
            )
            self._stale_since = None
            return

        max_drift = 0.0
        drifted_ids: list[int] = []
        for marker_id, expected in calibrated_centers.items():
            actual = detected_by_id[marker_id]
            dx = actual[0] - expected[0]
            dy = actual[1] - expected[1]
            drift = math.hypot(dx, dy)
            if drift > max_drift:
                max_drift = drift
            if drift > DRIFT_THRESHOLD_PX:
                drifted_ids.append(marker_id)

        now = time.monotonic()
        if not drifted_ids:
            self._stale_since = None
            return

        if self._stale_since is None:
            self._stale_since = now
            await self._publish(
                {
                    "event": "workspace.stale",
                    "drifted": sorted(drifted_ids),
                    "max_drift_px": round(max_drift, 2),
                }
            )
            log.info(
                "workspace.stale",
                drifted=sorted(drifted_ids),
                max_drift_px=round(max_drift, 2),
            )
            return

        if now - self._stale_since < STALE_PERSIST_S:
            return

        log.info(
            "calibration_watcher.auto_recalibrating",
            drifted=sorted(drifted_ids),
            max_drift_px=round(max_drift, 2),
        )
        try:
            centers = await run_full_recalibration(state)
        except CalibrationFailure as exc:
            log.warning(
                "recalibrate.deferred",
                reason=exc.code,
                detail=str(exc),
            )
            # Reset so we re-trigger on the next sustained drift window
            # rather than spamming attempts every tick.
            self._stale_since = None
            self._recal_cooldown_until = now + CHECK_INTERVAL_S * 2
            return

        self._stale_since = None
        self._recal_cooldown_until = now + CHECK_INTERVAL_S * 2
        await self._publish(
            {
                "event": "workspace.recalibrated",
                "markers": centers,
            }
        )

    async def _publish(self, event: dict[str, object]) -> None:
        events = getattr(self._app.state, "events", None)
        if events is None:
            return
        await events.publish(event)
