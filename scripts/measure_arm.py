"""Guided DH-parameter measurement.

Prompts the operator for four link lengths in mm, sanity checks the
result, and writes data/calibration/arm_dh.json. Run from the laptop or
the Pi; no hardware is touched.

Link conventions (matches docs/03_calibration_guide.md):
    L0  base   -> shoulder pivot   (vertical from table to shoulder)
    L1  shoulder -> elbow pivot
    L2  elbow  -> wrist pivot
    L3  wrist  -> gripper fingertips (closed)
"""

from __future__ import annotations

import json
import sys

from frankie.config import get_settings

PROMPTS = [
    ("L0_base_to_shoulder", "table surface -> center of shoulder pivot"),
    ("L1_shoulder_to_elbow", "shoulder pivot -> elbow pivot"),
    ("L2_elbow_to_wrist", "elbow pivot -> wrist pivot"),
    ("L3_wrist_to_gripper", "wrist pivot -> gripper fingertips (closed)"),
]


def _ask_mm(prompt: str) -> float:
    while True:
        s = input(f"  {prompt} (mm): ").strip()
        try:
            value = float(s)
        except ValueError:
            print("    not a number, try again.")
            continue
        if value <= 0 or value > 500:
            print("    out of plausible range (0-500mm). try again.")
            continue
        return value


def main() -> int:
    """Walk the four prompts, save JSON."""
    print("\nFrankie arm measurement")
    print("--------------------------------")
    print("Power off the SoulBay rail. Move the arm to vertical, joints aligned.")
    print("Measure each segment between joint pivots, in millimeters.\n")

    values: dict[str, float] = {}
    for key, description in PROMPTS:
        values[key] = _ask_mm(description)

    arm_reach = values["L1_shoulder_to_elbow"] + values["L2_elbow_to_wrist"] + values["L3_wrist_to_gripper"]
    print(f"\nshoulder -> fingertip reach: {arm_reach:.0f} mm")
    if not (180 <= arm_reach <= 320):
        print("WARNING: reach falls outside the expected 180-320mm range.")
        print("         re-measure if this is surprising.")

    settings = get_settings()
    out = settings.calibration_dir / "arm_dh.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, **values}
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nsaved {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
