"""ArUco marker generation and detection (DICT_4X4_50).

Used for workspace homography (IDs 0-3) and the chess board corners
(IDs 4-7). generate_marker_pdf produces a printable A4 PDF; detect_markers
returns the sub-pixel corners.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel

ARUCO_DICT = cv2.aruco.DICT_4X4_50

# A4 at 300dpi
PAGE_W_MM = 210
PAGE_H_MM = 297
DPI = 300
MM_PER_INCH = 25.4

# Default workspace marker placement in (X_mm forward, Y_mm left/right) from
# arm base center on the table surface.
DEFAULT_MARKER_WORLD_XY_MM: dict[int, tuple[float, float]] = {
    0: (30.0, -130.0),
    1: (30.0, +130.0),
    2: (150.0, +130.0),
    3: (150.0, -130.0),
}


class ArucoDetection(BaseModel):
    """One detected marker."""

    id: int
    corners_px: list[tuple[float, float]]
    center_px: tuple[float, float]


def _mm_to_px(mm: float) -> int:
    return round(mm / MM_PER_INCH * DPI)


def _marker_image(marker_id: int, side_mm: float) -> Image.Image:
    """Render a single ArUco marker as a PIL image with a small quiet zone."""
    side_px = _mm_to_px(side_mm)
    aruco_dict = cv2.aruco.getPredefinedDictionary(ARUCO_DICT)
    img = cv2.aruco.generateImageMarker(aruco_dict, marker_id, side_px)
    # ArUco needs a white quiet zone around it (at least 1 module). Make it 10% wide.
    pad_px = max(8, side_px // 10)
    canvas = np.full((side_px + 2 * pad_px, side_px + 2 * pad_px), 255, dtype=np.uint8)
    canvas[pad_px : pad_px + side_px, pad_px : pad_px + side_px] = img
    return Image.fromarray(canvas).convert("RGB")


def _load_font(size_px: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Try a TrueType font for crisp labels; fall back to PIL's default bitmap font."""
    for candidate in (
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ):
        try:
            return ImageFont.truetype(candidate, size_px)
        except OSError:
            continue
    return ImageFont.load_default()


def generate_marker_pdf(
    marker_ids: list[int],
    size_mm: float,
    output_path: Path,
    world_xy_mm: dict[int, tuple[float, float]] | None = None,
) -> None:
    """Write a printable A4 PDF of ArUco markers to output_path.

    Each marker is rendered at *exactly* size_mm on a 300dpi page so a
    print-at-actual-size run produces the right physical dimensions.
    Markers are labeled with their ID and intended world XY coordinates.
    """
    if world_xy_mm is None:
        world_xy_mm = DEFAULT_MARKER_WORLD_XY_MM

    page_w_px = _mm_to_px(PAGE_W_MM)
    page_h_px = _mm_to_px(PAGE_H_MM)
    page = Image.new("RGB", (page_w_px, page_h_px), "white")
    draw = ImageDraw.Draw(page)

    title_font = _load_font(60)
    body_font = _load_font(34)
    label_font = _load_font(40)

    margin = _mm_to_px(15)
    y = margin

    draw.text((margin, y), "Frankie Workspace Markers", fill="black", font=title_font)
    y += 80

    body_lines = [
        "Print at 100% / actual size. Do NOT 'fit to page'.",
        f"Each marker is {int(size_mm)}mm on a side. Verify with a ruler before taping.",
        "Cut along the dashed borders. Tape each marker flat on the workspace",
        "at the (X, Y) shown below. X is forward from the arm base, Y is",
        "left (negative) / right (positive). Coordinates are in mm.",
    ]
    for line in body_lines:
        draw.text((margin, y), line, fill="black", font=body_font)
        y += 44
    y += 30

    # Arrange 4 markers in a 2x2 grid below the instructions.
    marker_box_mm = size_mm + 24  # marker + label gutter
    marker_box_px = _mm_to_px(marker_box_mm)
    grid_origin_x = margin
    grid_origin_y = y

    for index, marker_id in enumerate(marker_ids):
        col = index % 2
        row = index // 2
        cell_x = grid_origin_x + col * (marker_box_px + _mm_to_px(20))
        cell_y = grid_origin_y + row * (marker_box_px + _mm_to_px(20))

        marker_img = _marker_image(marker_id, size_mm)
        page.paste(marker_img, (cell_x, cell_y))

        coord = world_xy_mm.get(marker_id)
        coord_text = f"X={coord[0]:.0f}  Y={coord[1]:+.0f}" if coord else "(unassigned)"
        label_y = cell_y + marker_img.size[1] + 6
        draw.text((cell_x, label_y), f"ID {marker_id}", fill="black", font=label_font)
        draw.text(
            (cell_x, label_y + 50),
            coord_text,
            fill="black",
            font=label_font,
        )

        # Dashed cut border around the marker image area.
        bbox = (cell_x - 6, cell_y - 6, cell_x + marker_img.size[0] + 6, cell_y + marker_img.size[1] + 6)
        _draw_dashed_rect(draw, bbox, dash_len=18, gap_len=14)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    page.save(output_path, "PDF", resolution=float(DPI))


def _draw_dashed_rect(
    draw: ImageDraw.ImageDraw,
    bbox: tuple[int, int, int, int],
    dash_len: int,
    gap_len: int,
) -> None:
    x0, y0, x1, y1 = bbox
    width = 3
    # top & bottom
    for y in (y0, y1):
        x = x0
        while x < x1:
            draw.line([(x, y), (min(x + dash_len, x1), y)], fill="black", width=width)
            x += dash_len + gap_len
    # left & right
    for x in (x0, x1):
        y = y0
        while y < y1:
            draw.line([(x, y), (x, min(y + dash_len, y1))], fill="black", width=width)
            y += dash_len + gap_len


def detect_markers(frame: np.ndarray) -> list[ArucoDetection]:
    """Detect every DICT_4X4_50 marker in frame, returning sorted by id."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame

    aruco_dict = cv2.aruco.getPredefinedDictionary(ARUCO_DICT)
    parameters = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(aruco_dict, parameters)
    corners, ids, _ = detector.detectMarkers(gray)

    out: list[ArucoDetection] = []
    if ids is None:
        return out
    for marker_id, corner in zip(ids.flatten(), corners, strict=True):
        pts = corner.reshape(4, 2)
        center = pts.mean(axis=0)
        out.append(
            ArucoDetection(
                id=int(marker_id),
                corners_px=[(float(p[0]), float(p[1])) for p in pts],
                center_px=(float(center[0]), float(center[1])),
            )
        )
    out.sort(key=lambda d: d.id)
    return out
