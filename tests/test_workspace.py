"""Workspace homography: save/load + round-trip + reachable-region check."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from frankie.vision.aruco import ARUCO_DICT, DEFAULT_MARKER_WORLD_XY_MM, detect_markers
from frankie.vision.workspace import (
    Workspace,
    WorkspaceCalibration,
    compute_workspace_from_detections,
    load_workspace,
    save_workspace,
)


def _synthetic_corners() -> np.ndarray:
    """Same fixed-corner frame as test_aruco for a stable homography."""
    frame = np.full((720, 1280, 3), 255, dtype=np.uint8)
    aruco_dict = cv2.aruco.getPredefinedDictionary(ARUCO_DICT)
    positions = [(180, 120), (920, 120), (920, 460), (180, 460)]
    for idx, marker_id in enumerate([0, 1, 2, 3]):
        x, y = positions[idx]
        marker = cv2.aruco.generateImageMarker(aruco_dict, marker_id, 200)
        frame[y : y + 200, x : x + 200] = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
    return frame


def test_workspace_calibration_round_trip() -> None:
    cal = WorkspaceCalibration(
        homography=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        marker_world_xy_mm={0: (100.0, -150.0)},
    )
    save_workspace(cal)
    loaded = load_workspace()
    assert loaded is not None
    assert loaded.marker_world_xy_mm[0] == (100.0, -150.0)


def test_homography_from_synthetic_round_trips() -> None:
    frame = _synthetic_corners()
    detections = detect_markers(frame)
    assert len(detections) == 4
    cal = compute_workspace_from_detections(detections)
    ws = Workspace(cal)
    # For each detected marker, pixel -> world should land within a few mm of
    # the configured target.
    for d in detections:
        world = ws.pixel_to_world(d.center_px)
        target = DEFAULT_MARKER_WORLD_XY_MM[d.id]
        assert abs(world[0] - target[0]) < 5.0
        assert abs(world[1] - target[1]) < 5.0


def test_reachable_region_bounds() -> None:
    cal = WorkspaceCalibration(
        homography=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        marker_world_xy_mm={},
    )
    ws = Workspace(cal)
    assert ws.is_in_reachable_region((150.0, 0.0))
    assert ws.is_in_reachable_region((80.0, -180.0))
    assert not ws.is_in_reachable_region((10.0, 0.0))
    assert not ws.is_in_reachable_region((250.0, 0.0))
    assert not ws.is_in_reachable_region((150.0, 300.0))


def test_compute_workspace_requires_four_markers() -> None:
    frame = np.full((720, 1280, 3), 255, dtype=np.uint8)
    with pytest.raises(ValueError):
        compute_workspace_from_detections(detect_markers(frame))
