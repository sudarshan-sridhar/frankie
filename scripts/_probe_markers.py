"""Grab one frame from the RTSP feed and report which ArUco markers are detected."""

from __future__ import annotations

import sys

import cv2

from frankie.config import get_settings
from frankie.vision.aruco import detect_markers


def main() -> int:
    s = get_settings()
    url = s.camera_url or "rtsp://127.0.0.1:8554/cam"
    print(f"opening {url}")
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        print("ERROR: could not open stream")
        return 1
    frame = None
    for _ in range(15):
        ok, f = cap.read()
        if ok:
            frame = f
    cap.release()
    if frame is None:
        print("ERROR: no frame")
        return 1
    print(f"frame shape: {frame.shape}")
    detections = detect_markers(frame)
    ids = sorted(d.id for d in detections)
    print(f"detected ids: {ids}")
    for d in detections:
        cx, cy = d.center_px
        print(f"  ID {d.id}: center_px=({cx:.0f}, {cy:.0f})")
    # save annotated preview
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
    out_path = "/tmp/_marker_probe.jpg"
    cv2.imwrite(out_path, annotated)
    print(f"saved annotated frame: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
