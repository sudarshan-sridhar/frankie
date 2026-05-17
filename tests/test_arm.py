"""Arm controller: ramp-to-target, gripper, e-stop semantics."""

from __future__ import annotations

import pytest

from frankie.hardware.arm import Arm
from frankie.hardware.calibration import default_calibration
from frankie.hardware.servo_driver import SimulatorServoDriver


@pytest.fixture()
def arm() -> Arm:
    driver = SimulatorServoDriver()
    cal = default_calibration()
    return Arm(driver=driver, calibration=cal, mode="simulator")


async def test_jog_joint_records_state_and_pulse(arm: Arm) -> None:
    await arm.jog_joint("shoulder", 30)
    state = arm.get_state()
    assert state.joints["shoulder"].angle_deg == 30
    # 30 deg on default calibration: 1500 + (30/90)*1000 = 1833
    assert 1820 <= state.joints["shoulder"].pulse_us <= 1850


async def test_jog_outside_limits_raises(arm: Arm) -> None:
    with pytest.raises(ValueError):
        await arm.jog_joint("shoulder", 999)


async def test_gripper_set_clamps_and_updates_state(arm: Arm) -> None:
    await arm.gripper_set(0.5)
    assert arm.get_state().gripper_ratio == 0.5

    await arm.gripper_set(2.0)  # over the top clamps to 1.0
    assert arm.get_state().gripper_ratio == 1.0

    await arm.gripper_set(-0.5)  # under zero clamps to 0.0
    assert arm.get_state().gripper_ratio == 0.0


async def test_estop_blocks_motion_until_cleared(arm: Arm) -> None:
    await arm.emergency_stop()
    assert arm.get_state().estopped is True
    with pytest.raises(RuntimeError):
        await arm.jog_joint("shoulder", 10)
    arm.clear_estop()
    assert arm.get_state().estopped is False
    await arm.jog_joint("shoulder", 10)  # works again


async def test_home_centers_every_joint(arm: Arm) -> None:
    await arm.jog_joint("shoulder", 45)
    await arm.jog_joint("elbow", -30)
    await arm.home()
    for j in ("base", "shoulder", "elbow", "wrist"):
        assert arm.get_state().joints[j].angle_deg == 0
    assert arm.get_state().gripper_ratio == 0
