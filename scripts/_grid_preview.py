"""Snapshot one frame with the grid overlay drawn so we can verify the homography."""

from __future__ import annotations

import cv2

from frankie.config import get_settings
from frankie.vision.workspace import (
    Workspace,
    draw_grid_overlay,
    load_workspace,
)


def main() -> int:
    s = get_settings()
    cal = load_workspace()
    if cal is None:
        print("ERROR: no workspace.json saved yet")
        return 1
    cap = cv2.VideoCapture(s.camera_url or "rtsp://127.0.0.1:8554/cam", cv2.CAP_FFMPEG)
    frame = None
    for _ in range(15):
        ok, f = cap.read()
        if ok:
            frame = f
    cap.release()
    if frame is None:
        print("ERROR: no frame")
        return 1
    ws = Workspace(cal)
    overlay = draw_grid_overlay(frame, ws)
    out = "/tmp/_grid_preview.jpg"
    cv2.imwrite(out, overlay)
    print(f"saved {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
