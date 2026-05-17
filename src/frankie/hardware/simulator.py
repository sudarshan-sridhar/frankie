"""Simulator helpers for laptop development without hardware.

The simulator ServoDriver lives in servo_driver.py; this module collects
higher-level fakes (timing, fake arm state) used by tests and the laptop
dev loop. Phase 1 leaves the body as a stub.
"""

from __future__ import annotations


class SimulatedArm:
    """Coarse stand-in used when no PCA9685 is present."""

    def __init__(self) -> None:
        raise NotImplementedError
