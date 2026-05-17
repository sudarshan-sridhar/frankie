"""Produce data/calibration/markers.pdf for printing.

Run on the laptop:
    uv run python scripts/generate_markers.py

The output is an A4 PDF with 4 ArUco markers (IDs 0-3, 30mm) and the
intended workspace (X, Y) coordinates printed below each. Print it at
100% / actual-size.
"""

from __future__ import annotations

import sys

from frankie.config import get_settings
from frankie.vision.aruco import (
    DEFAULT_MARKER_WORLD_XY_MM,
    generate_marker_pdf,
)

SIZE_MM = 30.0


def main() -> int:
    """Render markers PDF using default 4-corner workspace layout."""
    settings = get_settings()
    out = settings.calibration_dir / "markers.pdf"
    generate_marker_pdf(
        marker_ids=sorted(DEFAULT_MARKER_WORLD_XY_MM),
        size_mm=SIZE_MM,
        output_path=out,
    )
    print(f"wrote: {out}")
    print(f"  4 markers, {int(SIZE_MM)}mm each")
    print("  print at 100% / actual size (NOT 'fit to page')")
    print("  workspace placement:")
    for mid, (x, y) in sorted(DEFAULT_MARKER_WORLD_XY_MM.items()):
        print(f"    ID {mid}: X={x:.0f}mm  Y={y:+.0f}mm")
    return 0


if __name__ == "__main__":
    sys.exit(main())
