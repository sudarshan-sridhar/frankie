"""Pixel to world-coordinate mapping for the workspace.

A homography computed from 4 ArUco markers at known XY mm coordinates lets
the frontend project a click into the arm's coordinate frame. Z is fixed
at the table surface (Z=0) for click-to-move; modes that need a Z offset
apply it themselves.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import cv2
import numpy as np
import structlog
from pydantic import BaseModel, Field

from frankie.config import get_settings
from frankie.vision.aruco import (
    DEFAULT_MARKER_WORLD_XY_MM,
    ArucoDetection,
    detect_markers,
)

if TYPE_CHECKING:
    from numpy.typing import NDArray

log = structlog.get_logger(__name__)


class WorkspaceCalibration(BaseModel):
    """Persisted homography + the marker positions used to compute it."""

    homography: list[list[float]]
    marker_world_xy_mm: dict[int, tuple[float, float]]
    marker_pixel_centers: dict[int, tuple[float, float]] = Field(default_factory=dict)
    reachable_x_mm: tuple[float, float] = Field(default=(20.0, 160.0))
    reachable_y_mm: tuple[float, float] = Field(default=(-135.0, 135.0))


def workspace_calibration_path() -> Path:
    """Disk location for the workspace calibration JSON."""
    return get_settings().calibration_dir / "workspace.json"


def load_workspace() -> WorkspaceCalibration | None:
    """Read the saved calibration, returning None if it does not exist."""
    path = workspace_calibration_path()
    if not path.exists():
        return None
    return WorkspaceCalibration.model_validate_json(path.read_text(encoding="utf-8"))


def save_workspace(cal: WorkspaceCalibration) -> None:
    """Persist the calibration to data/calibration/workspace.json."""
    path = workspace_calibration_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(cal.model_dump_json(indent=2), encoding="utf-8")


def compute_workspace_from_detections(
    detections: list[ArucoDetection],
    world_xy_mm: dict[int, tuple[float, float]] | None = None,
) -> WorkspaceCalibration:
    """Solve the homography given detected markers and known world positions.

    Requires at least 4 markers whose IDs appear in ``world_xy_mm``.
    """
    world = world_xy_mm or DEFAULT_MARKER_WORLD_XY_MM
    pts_px: list[tuple[float, float]] = []
    pts_world: list[tuple[float, float]] = []
    pixel_centers: dict[int, tuple[float, float]] = {}
    for d in detections:
        if d.id in world:
            pts_px.append(d.center_px)
            pts_world.append(world[d.id])
            pixel_centers[int(d.id)] = (float(d.center_px[0]), float(d.center_px[1]))
    if len(pts_px) < 4:
        raise ValueError(
            f"need at least 4 known markers, got {len(pts_px)} "
            f"(detected ids: {sorted(d.id for d in detections)})"
        )

    src = np.asarray(pts_px, dtype=np.float32)
    dst = np.asarray(pts_world, dtype=np.float32)
    h, _ = cv2.findHomography(src, dst, method=0)
    if h is None:
        raise RuntimeError("findHomography returned None")
    return WorkspaceCalibration(
        homography=h.tolist(),
        marker_world_xy_mm={int(k): tuple(world[k]) for k in world},
        marker_pixel_centers=pixel_centers,
    )


class Workspace:
    """Bound to a WorkspaceCalibration; maps pixels to world XY mm."""

    def __init__(self, calibration: WorkspaceCalibration) -> None:
        self._cal = calibration
        self._h = np.asarray(calibration.homography, dtype=np.float64)
        self._h_inv = np.linalg.inv(self._h)

    @property
    def calibration(self) -> WorkspaceCalibration:
        return self._cal

    def pixel_to_world(self, px: tuple[float, float]) -> tuple[float, float]:
        """Project pixel (x, y) into world (X, Y) mm at the table surface."""
        vec = np.asarray([px[0], px[1], 1.0], dtype=np.float64)
        out = self._h @ vec
        return (float(out[0] / out[2]), float(out[1] / out[2]))

    def world_to_pixel(self, world_xy: tuple[float, float]) -> tuple[float, float]:
        """Inverse of pixel_to_world for overlay rendering."""
        vec = np.asarray([world_xy[0], world_xy[1], 1.0], dtype=np.float64)
        out = self._h_inv @ vec
        return (float(out[0] / out[2]), float(out[1] / out[2]))

    def is_in_reachable_region(self, world_xy: tuple[float, float]) -> bool:
        """True if (X, Y) lies inside the configured reachable rectangle."""
        x, y = world_xy
        xlo, xhi = self._cal.reachable_x_mm
        ylo, yhi = self._cal.reachable_y_mm
        return xlo <= x <= xhi and ylo <= y <= yhi


def calibrate_from_frame(frame: NDArray[np.uint8]) -> WorkspaceCalibration:
    """One-shot helper: detect markers in frame + compute calibration."""
    detections = detect_markers(frame)
    cal = compute_workspace_from_detections(detections)
    log.info("workspace.calibrated", markers=sorted(d.id for d in detections))
    return cal


def draw_grid_overlay(
    frame: NDArray[np.uint8],
    workspace: Workspace,
    *,
    color: tuple[int, int, int] = (0, 255, 255),
    step_mm: int = 30,
) -> NDArray[np.uint8]:
    """Project a world-coord grid through the homography onto the frame.

    Lines are drawn every ``step_mm`` over the reachable rectangle. Major
    junctions are labelled with their world (X, Y) in mm so the user can
    see where physical points map to in the camera view.
    """
    cal = workspace.calibration
    xlo, xhi = cal.reachable_x_mm
    ylo, yhi = cal.reachable_y_mm
    h, w = frame.shape[:2]
    out = frame.copy()

    def _project(x_mm: float, y_mm: float) -> tuple[int, int] | None:
        px = workspace.world_to_pixel((x_mm, y_mm))
        ix, iy = int(round(px[0])), int(round(px[1]))
        if -2000 < ix < w + 2000 and -2000 < iy < h + 2000:
            return ix, iy
        return None

    # vertical lines (constant X, sweep Y)
    x_lines = list(range(int(xlo), int(xhi) + 1, step_mm))
    if x_lines and x_lines[-1] != int(xhi):
        x_lines.append(int(xhi))
    for x_mm in x_lines:
        pts: list[tuple[int, int]] = []
        y = ylo
        while y <= yhi:
            p = _project(x_mm, y)
            if p is not None:
                pts.append(p)
            y += 5.0
        for a, b in zip(pts, pts[1:], strict=False):
            cv2.line(out, a, b, color, 1, cv2.LINE_AA)

    # horizontal lines (constant Y, sweep X)
    y_lines = list(range(int(ylo), int(yhi) + 1, step_mm))
    if y_lines and y_lines[-1] != int(yhi):
        y_lines.append(int(yhi))
    for y_mm in y_lines:
        pts = []
        x = xlo
        while x <= xhi:
            p = _project(x, y_mm)
            if p is not None:
                pts.append(p)
            x += 5.0
        for a, b in zip(pts, pts[1:], strict=False):
            cv2.line(out, a, b, color, 1, cv2.LINE_AA)

    # base origin marker
    origin = _project(0.0, 0.0)
    if origin is not None:
        cv2.drawMarker(out, origin, (0, 0, 255), cv2.MARKER_CROSS, 16, 2)
        cv2.putText(out, "base", (origin[0] + 8, origin[1] + 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1, cv2.LINE_AA)

    # labels at the 4 grid corners
    for (x_mm, y_mm) in (
        (int(xlo), int(ylo)),
        (int(xlo), int(yhi)),
        (int(xhi), int(ylo)),
        (int(xhi), int(yhi)),
    ):
        p = _project(float(x_mm), float(y_mm))
        if p is None:
            continue
        cv2.circle(out, p, 3, color, -1)
        cv2.putText(out, f"({x_mm},{y_mm})", (p[0] + 6, p[1] - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)

    return out
