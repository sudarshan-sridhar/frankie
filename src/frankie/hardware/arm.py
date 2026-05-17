"""High-level arm controller.

Wraps a ServoDriver and CalibrationData to expose joint-name and gripper
operations. All motion methods are async; large jumps are split into
small steps with awaits so the event loop never blocks for long.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import structlog

from frankie.hardware.calibration import (
    CalibrationData,
    GripperCalibration,
    JointCalibration,
    pulse_for_angle,
    pulse_for_gripper_ratio,
)
from frankie.hardware.servo_driver import ServoDriver
from frankie.safety import SafetyMonitor
from frankie.state import ArmState, JointState

if TYPE_CHECKING:
    from frankie.hardware.kinematics import Kinematics

log = structlog.get_logger(__name__)


JOG_STEP_DEG: float = 2.0
JOG_SLEEP_S: float = 0.02
RAMP_HOME_STEP_DEG: float = 2.0

# Defaults validated on hardware in Task #43 + #45 (pick-and-place dry run).
# pick_z=10 worked at the workspace centre in manual tests but bottomed out
# at off-centre positions because the IK pose changes and joint overshoots
# compound differently. 15 mm clears the table everywhere we tested while
# still being below the typical ~3 cm cube body height for a reliable grab.
# place_z is higher because the gripper is *holding* the cube on descent
# (effective tip lower by ~half the cube).
DEFAULT_APPROACH_Z_MM: float = 60.0
DEFAULT_PICK_Z_MM: float = 15.0
DEFAULT_PLACE_Z_MM: float = 20.0
# Lift this high between pick and traverse so the carried object clears
# any other items still on the bench. Tuned on bench: 120 was reaching the
# top of the IK envelope and failing pickups; 100 gives clearance over
# other tools without losing reach reliability.
DEFAULT_TRANSIT_Z_MM: float = 100.0
GRIPPER_SETTLE_S: float = 0.4
# A deliberate pre-release pause that reads as "gentle" on hand-offs.
GENTLE_RELEASE_PAUSE_S: float = 0.6


class Arm:
    """Arm controller bound to a driver and calibration."""

    def __init__(
        self,
        driver: ServoDriver,
        calibration: CalibrationData,
        safety: SafetyMonitor | None = None,
        mode: str = "simulator",
    ) -> None:
        self._driver = driver
        self._cal = calibration
        self._safety = safety or SafetyMonitor.from_calibration(calibration)
        self._lock = asyncio.Lock()
        self._state = ArmState(mode="hardware" if mode == "hardware" else "simulator")
        self._last_angle_deg: dict[str, float] = {}
        self._last_gripper_ratio: float = 0.0
        self._estopped = False
        self._seed_state()

    def _seed_state(self) -> None:
        for ch_str, entry in self._cal.channels.items():
            if isinstance(entry, JointCalibration):
                self._last_angle_deg[entry.name] = 0.0
                self._state.joints[entry.name] = JointState(
                    name=entry.name,
                    angle_deg=0.0,
                    pulse_us=entry.pulse_center,
                )
            elif isinstance(entry, GripperCalibration):
                self._state.gripper_ratio = 0.0
            # ch_str unused, but channel order is preserved by the dict
            _ = ch_str

    async def home(self) -> None:
        """Move every joint to its calibrated center, ramped slowly."""
        if self._estopped:
            raise RuntimeError("arm is e-stopped; clear estop before motion")
        async with self._lock:
            for entry in self._cal.channels.values():
                if isinstance(entry, JointCalibration):
                    await self._ramp_joint(entry.name, 0.0, step_deg=RAMP_HOME_STEP_DEG)
            await self.gripper_set(0.0)
            log.info("arm.home.done")

    async def jog_joint(self, joint_name: str, angle_deg: float) -> None:
        """Command one joint to angle_deg with a slow ramp from its last setpoint."""
        if self._estopped:
            raise RuntimeError("arm is e-stopped; clear estop before motion")
        if not self._safety.check_joint_limits(joint_name, angle_deg):
            raise ValueError(f"{joint_name}={angle_deg} outside safety limits")
        async with self._lock:
            await self._ramp_joint(joint_name, angle_deg, step_deg=JOG_STEP_DEG)

    async def gripper_open(self) -> None:
        """Fully open the gripper."""
        await self.gripper_set(0.0)

    async def gripper_close(self) -> None:
        """Fully close the gripper."""
        await self.gripper_set(1.0)

    async def gripper_set(self, ratio: float) -> None:
        """Set gripper to ratio in [0.0=open, 1.0=closed]."""
        if self._estopped:
            raise RuntimeError("arm is e-stopped; clear estop before motion")
        ratio = max(0.0, min(1.0, ratio))
        pulse = pulse_for_gripper_ratio(ratio, self._cal)
        gripper_channel = self._gripper_channel()
        self._driver.set_pulse_safe(gripper_channel, pulse, self._cal.get(gripper_channel))
        self._last_gripper_ratio = ratio
        self._state.gripper_ratio = ratio
        log.info("arm.gripper", ratio=ratio, pulse_us=pulse)

    async def emergency_stop(self) -> None:
        """Disable all PWM output. Arm goes limp."""
        self._estopped = True
        self._driver.disable_all()
        self._state.estopped = True
        log.warning("arm.estop")

    def clear_estop(self) -> None:
        """Allow motion again after an e-stop."""
        self._estopped = False
        self._state.estopped = False
        log.info("arm.estop.cleared")

    def get_state(self) -> ArmState:
        """Snapshot the latest commanded state."""
        return self._state.model_copy(deep=True)

    def reload_calibration(self, calibration: CalibrationData) -> None:
        """Swap in a new calibration without recreating the Arm.

        The internal SafetyMonitor is re-seeded so newly tightened (or
        widened) angle limits take effect immediately. Existing commanded
        joint positions are preserved.
        """
        self._cal = calibration
        self._safety = SafetyMonitor.from_calibration(calibration)
        log.info("arm.calibration.reloaded", channels=len(calibration.channels))

    async def _ramp_joint(self, joint_name: str, target_deg: float, step_deg: float) -> None:
        channel = self._cal.channel_for_name(joint_name)
        entry = self._cal.get(channel)
        if not isinstance(entry, JointCalibration):
            raise TypeError(f"{joint_name} is not a joint")

        current = self._last_angle_deg.get(joint_name, 0.0)
        direction = 1.0 if target_deg >= current else -1.0
        position = current
        while abs(target_deg - position) > step_deg:
            position += direction * step_deg
            self._command_joint(joint_name, channel, entry, position)
            await asyncio.sleep(JOG_SLEEP_S)
        self._command_joint(joint_name, channel, entry, target_deg)

    def _command_joint(
        self,
        joint_name: str,
        channel: int,
        entry: JointCalibration,
        angle_deg: float,
    ) -> None:
        pulse = pulse_for_angle(channel, angle_deg, self._cal)
        self._driver.set_pulse_safe(channel, pulse, entry)
        self._safety.register_command(joint_name, angle_deg, time.monotonic())
        self._last_angle_deg[joint_name] = angle_deg
        self._state.joints[joint_name] = JointState(
            name=joint_name, angle_deg=angle_deg, pulse_us=pulse
        )

    def _gripper_channel(self) -> int:
        for ch_str, entry in self._cal.channels.items():
            if isinstance(entry, GripperCalibration):
                return int(ch_str)
        raise LookupError("no gripper channel in calibration")

    async def move_to_xyz(
        self,
        x_mm: float,
        y_mm: float,
        z_mm: float,
        kinematics: Kinematics,
    ) -> None:
        """Solve IK for the target world point and drive every joint there.

        Public helper for modes that need a single XYZ move (no gripper
        action). Pick/place use this under the hood.
        """
        target = (x_mm, y_mm, z_mm)
        if not kinematics.is_reachable(target):
            raise ValueError(f"target {target} unreachable")
        current = {name: j.angle_deg for name, j in self._state.joints.items()}
        angles = kinematics.inverse(target, initial_angles_deg=current)
        for joint in ("base", "shoulder", "elbow", "wrist"):
            await self.jog_joint(joint, angles[joint])

    async def pick_at(
        self,
        world_xy: tuple[float, float],
        kinematics: Kinematics,
        *,
        approach_z_mm: float = DEFAULT_APPROACH_Z_MM,
        pick_z_mm: float = DEFAULT_PICK_Z_MM,
        transit_z_mm: float | None = None,
        pre_open: bool = True,
    ) -> None:
        """Open → hover above (x, y, approach_z) → descend to pick_z → close → lift.

        ``transit_z_mm`` (if set) is the z reached AFTER the close, so the
        carried object clears anything else on the bench during traversal.
        Defaults to ``approach_z_mm`` for back-compat with single-object picks.
        """
        x, y = world_xy
        if pre_open:
            await self.gripper_open()
            await asyncio.sleep(GRIPPER_SETTLE_S)
        await self.move_to_xyz(x, y, approach_z_mm, kinematics)
        await self.move_to_xyz(x, y, pick_z_mm, kinematics)
        await self.gripper_close()
        await asyncio.sleep(GRIPPER_SETTLE_S)
        lift_z = transit_z_mm if transit_z_mm is not None else approach_z_mm
        # IK can fold below min reach for points close to the base column. If
        # the requested transit height is unreachable for this XY, gracefully
        # fall back to the approach height so the pickup doesn't crash with a
        # cube/tool still in the gripper.
        try:
            await self.move_to_xyz(x, y, lift_z, kinematics)
        except ValueError:
            log.warning("arm.pick_at.transit_unreachable_fallback",
                        world_xy=[x, y], wanted=lift_z, fallback=approach_z_mm)
            await self.move_to_xyz(x, y, approach_z_mm, kinematics)
        log.info("arm.pick_at.done", world_xy=[x, y], transit_z=lift_z)

    async def place_at(
        self,
        world_xy: tuple[float, float],
        kinematics: Kinematics,
        *,
        approach_z_mm: float = DEFAULT_APPROACH_Z_MM,
        place_z_mm: float = DEFAULT_PLACE_Z_MM,
        transit_z_mm: float | None = None,
        gentle: bool = False,
    ) -> None:
        """Hover above (x, y, approach_z) → descend to place_z → open → lift.

        ``transit_z_mm`` (if set) is the z used to APPROACH the drop site so
        the carried object stays high until it's over the target. ``gentle``
        adds a pre-release pause so the drop reads as deliberate.
        """
        x, y = world_xy
        approach_z = transit_z_mm if transit_z_mm is not None else approach_z_mm
        # Same graceful fallback as pick_at — if the transit height pushes
        # the arm inside its min-reach fold sphere, descend from the
        # standard approach height instead.
        try:
            await self.move_to_xyz(x, y, approach_z, kinematics)
        except ValueError:
            log.warning("arm.place_at.transit_unreachable_fallback",
                        world_xy=[x, y], wanted=approach_z, fallback=approach_z_mm)
            await self.move_to_xyz(x, y, approach_z_mm, kinematics)
        await self.move_to_xyz(x, y, place_z_mm, kinematics)
        if gentle:
            await asyncio.sleep(GENTLE_RELEASE_PAUSE_S)
        await self.gripper_open()
        await asyncio.sleep(GRIPPER_SETTLE_S)
        await self.move_to_xyz(x, y, approach_z_mm, kinematics)
        log.info("arm.place_at.done", world_xy=[x, y], gentle=gentle)
