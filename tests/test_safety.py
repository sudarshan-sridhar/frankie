"""SafetyMonitor: limit checks and command bookkeeping."""

from __future__ import annotations

from frankie.hardware.calibration import default_calibration
from frankie.safety import JointLimit, SafetyMonitor


def test_safety_from_calibration_seeds_joint_limits() -> None:
    cal = default_calibration()
    monitor = SafetyMonitor.from_calibration(cal)
    assert set(monitor.limits) == {"wrist", "elbow", "shoulder", "base"}
    assert monitor.limits["shoulder"].min_deg == -90
    assert monitor.limits["shoulder"].max_deg == 90


def test_check_within_and_outside_limits() -> None:
    monitor = SafetyMonitor(
        limits={"shoulder": JointLimit(name="shoulder", min_deg=-45, max_deg=60)}
    )
    assert monitor.check_joint_limits("shoulder", 0) is True
    assert monitor.check_joint_limits("shoulder", 60) is True
    assert monitor.check_joint_limits("shoulder", -46) is False
    assert monitor.check_joint_limits("shoulder", 61) is False


def test_unknown_joint_is_rejected() -> None:
    monitor = SafetyMonitor()
    assert monitor.check_joint_limits("ghost", 0) is False


def test_record_now_stores_command() -> None:
    monitor = SafetyMonitor()
    monitor.record_now("shoulder", 12.5)
    rec = monitor.recent["shoulder"]
    assert rec.target_deg == 12.5
    assert rec.monotonic_time > 0
