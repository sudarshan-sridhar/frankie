"""Calibration schema, load/save round-trip, and pulse math."""

from __future__ import annotations

import pytest

from frankie.hardware.calibration import (
    GripperCalibration,
    JointCalibration,
    default_calibration,
    load_calibration,
    pulse_for_angle,
    pulse_for_gripper,
    pulse_for_gripper_ratio,
    save_calibration,
)


def test_default_calibration_has_five_channels() -> None:
    cal = default_calibration()
    assert set(cal.channels) == {"0", "1", "2", "3", "4"}
    assert isinstance(cal.get(0), GripperCalibration)
    for ch in (1, 2, 3, 4):
        assert isinstance(cal.get(ch), JointCalibration)


def test_save_then_load_round_trip() -> None:
    cal = default_calibration()
    cal.channels["3"] = JointCalibration(
        servo="LDX-218",
        name="shoulder",
        pulse_min=510,
        pulse_max=2510,
        pulse_center=1480,
        angle_min_deg=-80,
        angle_max_deg=80,
        inverted=True,
    )
    save_calibration(cal)
    reloaded = load_calibration()
    shoulder = reloaded.get(3)
    assert isinstance(shoulder, JointCalibration)
    assert shoulder.pulse_min == 510
    assert shoulder.pulse_center == 1480
    assert shoulder.inverted is True


def test_pulse_for_angle_endpoints_and_midpoint() -> None:
    cal = default_calibration()
    # shoulder: -90 -> 500, 0 -> 1500, +90 -> 2500
    assert pulse_for_angle(3, -90, cal) == 500
    assert pulse_for_angle(3, 0, cal) == 1500
    assert pulse_for_angle(3, 90, cal) == 2500


def test_pulse_for_angle_inverted_swaps_direction() -> None:
    cal = default_calibration()
    shoulder = cal.get(3)
    assert isinstance(shoulder, JointCalibration)
    shoulder.inverted = True
    # -90 maps to pulse_max instead of pulse_min
    assert pulse_for_angle(3, -90, cal) == 2500
    assert pulse_for_angle(3, 90, cal) == 500


def test_pulse_for_angle_clamps_out_of_range() -> None:
    cal = default_calibration()
    p = pulse_for_angle(3, 5000, cal)
    assert p == 2500


def test_pulse_for_angle_rejects_gripper_channel() -> None:
    cal = default_calibration()
    with pytest.raises(TypeError):
        pulse_for_angle(0, 0, cal)


def test_pulse_for_gripper_open_and_closed() -> None:
    cal = default_calibration()
    assert pulse_for_gripper(open_=True, cal=cal) == 1000
    assert pulse_for_gripper(open_=False, cal=cal) == 2000


def test_pulse_for_gripper_ratio_midpoint() -> None:
    cal = default_calibration()
    assert pulse_for_gripper_ratio(0.0, cal) == 1000
    assert pulse_for_gripper_ratio(1.0, cal) == 2000
    assert pulse_for_gripper_ratio(0.5, cal) == 1500


def test_channel_for_name_lookup() -> None:
    cal = default_calibration()
    assert cal.channel_for_name("base") == 4
    assert cal.channel_for_name("gripper") == 0
