"""ArUco generation and detection on synthetic frames."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from frankie.vision.aruco import (
    ARUCO_DICT,
    DEFAULT_MARKER_WORLD_XY_MM,
    detect_markers,
    generate_marker_pdf,
)


def _synthetic_frame(marker_ids: list[int], side_px: int = 200) -> np.ndarray:
    """Render markers onto a 1280x720 white frame at fixed positions."""
    frame = np.full((720, 1280, 3), 255, dtype=np.uint8)
    aruco_dict = cv2.aruco.getPredefinedDictionary(ARUCO_DICT)
    positions = [(180, 120), (920, 120), (920, 460), (180, 460)]
    for idx, marker_id in enumerate(marker_ids):
        x, y = positions[idx]
        marker = cv2.aruco.generateImageMarker(aruco_dict, marker_id, side_px)
        marker_bgr = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
        frame[y : y + side_px, x : x + side_px] = marker_bgr
    return frame


def test_detect_finds_all_markers() -> None:
    frame = _synthetic_frame([0, 1, 2, 3])
    detections = detect_markers(frame)
    assert sorted(d.id for d in detections) == [0, 1, 2, 3]
    for d in detections:
        assert len(d.corners_px) == 4
        cx, cy = d.center_px
        assert 0 < cx < 1280
        assert 0 < cy < 720


def test_detect_empty_frame_returns_empty() -> None:
    frame = np.full((720, 1280, 3), 255, dtype=np.uint8)
    assert detect_markers(frame) == []


def test_generate_marker_pdf_writes_file(tmp_path: Path) -> None:
    out = tmp_path / "markers.pdf"
    generate_marker_pdf(
        marker_ids=sorted(DEFAULT_MARKER_WORLD_XY_MM),
        size_mm=30.0,
        output_path=out,
    )
    assert out.exists()
    assert out.stat().st_size > 5000
