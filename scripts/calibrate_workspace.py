"""Capture a frame and compute the workspace homography.

Runs on the Pi (`make calibrate-workspace`). Reads CAMERA_URL from .env,
opens the stream, grabs a few frames to warm it up, detects all 4 ArUco
markers, and writes data/calibration/workspace.json.

Saves an annotated preview to data/calibration/workspace_preview.jpg so
you can verify the detected markers landed where you intended.
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2

from frankie.config import get_settings
from frankie.vision.aruco import detect_markers
from frankie.vision.workspace import (
    compute_workspace_from_detections,
    save_workspace,
)

WARMUP_FRAMES = 10
MAX_FRAMES = 30


def _grab_frame(url: str) -> cv2.Mat | None:
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        return None
    try:
        frame = None
        for i in range(MAX_FRAMES):
            ok, f = cap.read()
            if ok and f is not None and i >= WARMUP_FRAMES:
                frame = f
                break
        return frame
    finally:
        cap.release()


def main() -> int:
    """Entry point: grab a frame, calibrate, persist."""
    settings = get_settings()
    url = settings.camera_url or "rtsp://127.0.0.1:8554/cam"
    print(f"opening {url}...")
    frame = _grab_frame(url)
    if frame is None:
        print("ERROR: no frame from camera. Is Larix streaming?")
        return 1
    print(f"frame: {frame.shape[1]}x{frame.shape[0]}")

    detections = detect_markers(frame)
    detected_ids = sorted(d.id for d in detections)
    print(f"detected markers: {detected_ids}")
    if set(detected_ids) < {0, 1, 2, 3}:
        missing = sorted({0, 1, 2, 3} - set(detected_ids))
        print(f"ERROR: missing markers {missing}. Reposition the camera or the markers.")
        return 1

    cal = compute_workspace_from_detections(detections)
    save_workspace(cal)
    print(f"saved {settings.calibration_dir / 'workspace.json'}")

    # Annotated preview for sanity checking.
    preview_path: Path = settings.calibration_dir / "workspace_preview.jpg"
    annotated = frame.copy()
    for d in detections:
        pts = [(int(x), int(y)) for x, y in d.corners_px]
        for i in range(4):
            cv2.line(annotated, pts[i], pts[(i + 1) % 4], (0, 255, 0), 2)
        cx, cy = int(d.center_px[0]), int(d.center_px[1])
        cv2.circle(annotated, (cx, cy), 6, (0, 0, 255), -1)
        cv2.putText(
            annotated, f"ID {d.id}", (cx + 12, cy - 12),
            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2,
        )
    cv2.imwrite(str(preview_path), annotated)
    print(f"saved preview: {preview_path}")
    print("\ncalibration complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
