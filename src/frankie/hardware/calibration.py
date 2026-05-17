"""Servo calibration schema, on-disk format, and pulse math.

Calibration lives in data/calibration/servos.json. The file is hand-edited
only via scripts/calibrate_servos.py. Pydantic models below describe the
shape; default_calibration() seeds a safe starting point that homes every
joint to 1500us before per-channel tuning.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from frankie.config import get_settings


class JointCalibration(BaseModel):
    """Calibration for a rotational joint (base, shoulder, elbow, wrist)."""

    type: Literal["joint"] = "joint"
    servo: str
    name: str
    pulse_min: int
    pulse_max: int
    pulse_center: int
    angle_min_deg: float
    angle_max_deg: float
    inverted: bool = False


class GripperCalibration(BaseModel):
    """Calibration for the gripper channel."""

    type: Literal["gripper"] = "gripper"
    servo: str
    name: str
    pulse_min: int
    pulse_max: int
    pulse_center: int
    pulse_open: int
    pulse_closed: int
    inverted: bool = False


ChannelCalibration = JointCalibration | GripperCalibration


class CalibrationData(BaseModel):
    """Top-level on-disk calibration document."""

    version: int = 1
    channels: dict[str, ChannelCalibration]
    calibrated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    def channel_for_name(self, name: str) -> int:
        """Return the integer channel index for a joint/gripper name."""
        for ch_str, cal in self.channels.items():
            if cal.name == name:
                return int(ch_str)
        raise KeyError(f"no channel named {name!r}")

    def get(self, channel: int) -> ChannelCalibration:
        """Look up calibration by channel index."""
        return self.channels[str(channel)]


def _calibration_path() -> Path:
    return get_settings().calibration_dir / "servos.json"


def default_calibration() -> CalibrationData:
    """Conservative defaults matching the hardware wiring on channels 0-4."""
    return CalibrationData(
        channels={
            "0": GripperCalibration(
                servo="LFD-01M",
                name="gripper",
                pulse_min=600,
                pulse_max=2400,
                pulse_center=1500,
                pulse_open=1000,
                pulse_closed=2000,
            ),
            "1": JointCalibration(
                servo="LFD-01M",
                name="wrist",
                pulse_min=600,
                pulse_max=2400,
                pulse_center=1500,
                angle_min_deg=-90,
                angle_max_deg=90,
            ),
            "2": JointCalibration(
                servo="LFD-01M",
                name="elbow",
                pulse_min=600,
                pulse_max=2400,
                pulse_center=1500,
                angle_min_deg=-90,
                angle_max_deg=90,
            ),
            "3": JointCalibration(
                servo="LDX-218",
                name="shoulder",
                pulse_min=500,
                pulse_max=2500,
                pulse_center=1500,
                angle_min_deg=-90,
                angle_max_deg=90,
            ),
            "4": JointCalibration(
                servo="LD-1501MG",
                name="base",
                pulse_min=500,
                pulse_max=2500,
                pulse_center=1500,
                angle_min_deg=-90,
                angle_max_deg=90,
            ),
        }
    )


def load_calibration() -> CalibrationData:
    """Load calibration from disk, falling back to defaults if missing."""
    path = _calibration_path()
    if not path.exists():
        return default_calibration()
    return CalibrationData.model_validate_json(path.read_text(encoding="utf-8"))


def save_calibration(data: CalibrationData) -> None:
    """Persist calibration to disk, creating the calibration dir if needed."""
    data.calibrated_at = datetime.now(UTC).isoformat()
    path = _calibration_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data.model_dump_json(indent=2), encoding="utf-8")


def pulse_for_angle(channel: int, angle_deg: float, cal: CalibrationData) -> int:
    """Map angle_deg to a pulse width for a rotational joint.

    Linear interpolation from (angle_min_deg, angle_max_deg) onto
    (pulse_min, pulse_max). Honors the inverted flag. Result is clamped
    to the calibrated pulse bounds so a bad caller cannot drive past
    the mechanical limit.
    """
    entry = cal.get(channel)
    if not isinstance(entry, JointCalibration):
        raise TypeError(f"channel {channel} is not a joint")

    a0, a1 = entry.angle_min_deg, entry.angle_max_deg
    p0, p1 = entry.pulse_min, entry.pulse_max
    if entry.inverted:
        p0, p1 = p1, p0

    if a1 == a0:
        return entry.pulse_center

    angle = max(min(angle_deg, max(a0, a1)), min(a0, a1))
    fraction = (angle - a0) / (a1 - a0)
    pulse = p0 + fraction * (p1 - p0)
    return round(max(entry.pulse_min, min(entry.pulse_max, pulse)))


def pulse_for_gripper(open_: bool, cal: CalibrationData) -> int:
    """Return pulse_open or pulse_closed for the gripper channel."""
    entry = _find_gripper(cal)
    return entry.pulse_open if open_ else entry.pulse_closed


def pulse_for_gripper_ratio(ratio: float, cal: CalibrationData) -> int:
    """Map ratio in [0=open, 1=closed] to a pulse width for the gripper."""
    entry = _find_gripper(cal)
    ratio = max(0.0, min(1.0, ratio))
    pulse = entry.pulse_open + ratio * (entry.pulse_closed - entry.pulse_open)
    return round(max(entry.pulse_min, min(entry.pulse_max, pulse)))


def _find_gripper(cal: CalibrationData) -> GripperCalibration:
    for entry in cal.channels.values():
        if isinstance(entry, GripperCalibration):
            return entry
    raise LookupError("calibration has no gripper channel")
