"""Safety monitor.

Bounds-checks joint commands and records the latest command per joint
so a future watchdog can spot stalls. Phase 2 ships the synchronous
parts; the async watch() loop is a placeholder for Phase 3 stall logic.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import structlog

from frankie.hardware.calibration import CalibrationData, JointCalibration

log = structlog.get_logger(__name__)


@dataclass
class JointLimit:
    """Soft software limit for a single joint, in degrees from center."""

    name: str
    min_deg: float
    max_deg: float


@dataclass
class CommandRecord:
    """Last-known command for a joint."""

    joint: str
    target_deg: float
    monotonic_time: float


@dataclass
class SafetyMonitor:
    """Stateful safety checker. Holds limits and recent commands."""

    limits: dict[str, JointLimit] = field(default_factory=dict)
    recent: dict[str, CommandRecord] = field(default_factory=dict)

    @classmethod
    def from_calibration(cls, calibration: CalibrationData) -> SafetyMonitor:
        """Build a SafetyMonitor whose limits track the calibration bounds."""
        limits: dict[str, JointLimit] = {}
        for entry in calibration.channels.values():
            if isinstance(entry, JointCalibration):
                limits[entry.name] = JointLimit(
                    name=entry.name,
                    min_deg=entry.angle_min_deg,
                    max_deg=entry.angle_max_deg,
                )
        return cls(limits=limits)

    def check_joint_limits(self, joint: str, angle_deg: float) -> bool:
        """Return True if angle_deg is within configured limits for joint."""
        limit = self.limits.get(joint)
        if limit is None:
            log.warning("safety.no_limit", joint=joint)
            return False
        ok = limit.min_deg <= angle_deg <= limit.max_deg
        if not ok:
            log.warning(
                "safety.limit_exceeded",
                joint=joint,
                angle=angle_deg,
                min=limit.min_deg,
                max=limit.max_deg,
            )
        return ok

    def register_command(self, joint: str, target_deg: float, monotonic_time: float) -> None:
        """Record a freshly issued joint command."""
        self.recent[joint] = CommandRecord(
            joint=joint, target_deg=target_deg, monotonic_time=monotonic_time
        )

    def record_now(self, joint: str, target_deg: float) -> None:
        """Convenience: register_command with the current monotonic clock."""
        self.register_command(joint, target_deg, time.monotonic())

    async def watch(self) -> None:
        """Background task. Phase 3 will add stall and over-current detection."""
        log.info("safety.watch.started")
