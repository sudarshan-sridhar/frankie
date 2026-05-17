"""Probe detect_objects against the live camera; save an annotated preview."""

from __future__ import annotations

import cv2

from frankie.config import get_settings
from frankie.modes.defect import detect_objects
from frankie.vision.workspace import Workspace, load_workspace


def main() -> int:
    s = get_settings()
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

    ws_cal = load_workspace()
    workspace = Workspace(ws_cal) if ws_cal else None
    objects = detect_objects(frame, workspace=workspace)
    print(f"detected {len(objects)} objects")
    annotated = frame.copy()
    for i, c in enumerate(objects):
        x, y, w, h = c.bbox
        cv2.rectangle(annotated, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cx, cy = int(c.center_px[0]), int(c.center_px[1])
        cv2.circle(annotated, (cx, cy), 5, (0, 0, 255), -1)
        label = f"object {i} area={c.area_px:.0f}"
        cv2.putText(annotated, label, (x, y - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        print(f"  object {i}: bbox={c.bbox} center=({cx},{cy}) area={c.area_px:.0f}")
    out = "/tmp/_cube_probe.jpg"
    cv2.imwrite(out, annotated)
    print(f"saved {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
