"""Servo driver abstraction.

Defines the ServoDriver Protocol used by higher-level code, plus concrete
hardware (PCA9685 over I2C) and simulator implementations. get_servo_driver()
is the single decision point that picks one or the other at runtime; nothing
above this module imports adafruit libraries directly.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from frankie.hardware.calibration import ChannelCalibration


PCA9685_CHANNELS = 16

# PCA9685 PWM is 50Hz -> 20000us period; duty_cycle is a 16-bit value.
_PWM_PERIOD_US: float = 1_000_000.0 / 50.0
_DUTY_FULL_SCALE: int = 65535


def _pulse_us_to_duty(pulse_us: int) -> int:
    """Convert a microsecond pulse width into PCA9685 16-bit duty cycle."""
    if pulse_us <= 0:
        return 0
    duty = round(pulse_us / _PWM_PERIOD_US * _DUTY_FULL_SCALE)
    return max(0, min(_DUTY_FULL_SCALE, duty))


@runtime_checkable
class ServoDriver(Protocol):
    """Low-level PWM interface, one method per primitive."""

    def set_pulse(self, channel: int, pulse_us: int) -> None:
        """Set raw pulse width on a channel without bounds checks."""
        ...

    def set_pulse_safe(
        self, channel: int, pulse_us: int, calibration: ChannelCalibration
    ) -> None:
        """Set pulse clamped to the calibrated min/max for the channel."""
        ...

    def disable(self, channel: int) -> None:
        """Stop driving a channel (servo goes limp)."""
        ...

    def disable_all(self) -> None:
        """Stop driving every channel."""
        ...

    def is_real_hardware(self) -> bool:
        """True for HardwareServoDriver, False for SimulatorServoDriver."""
        ...


class HardwareServoDriver:
    """PCA9685-backed driver. Holds the I2C bus + PCA9685 object as singletons."""

    _instance: HardwareServoDriver | None = None
    _lock = threading.Lock()

    def __init__(self, address: int = 0x40, frequency_hz: int = 50) -> None:
        # Lazy import: the adafruit stack only loads on the Pi.
        import board
        import busio
        from adafruit_pca9685 import PCA9685

        i2c = busio.I2C(board.SCL, board.SDA)
        pca = PCA9685(i2c, address=address)
        pca.frequency = frequency_hz
        self._i2c = i2c
        self._pca: Any = pca
        self._address = address
        self._frequency_hz = frequency_hz

    def set_pulse(self, channel: int, pulse_us: int) -> None:
        self._guard_channel(channel)
        self._pca.channels[channel].duty_cycle = _pulse_us_to_duty(pulse_us)

    def set_pulse_safe(
        self, channel: int, pulse_us: int, calibration: ChannelCalibration
    ) -> None:
        self._guard_channel(channel)
        clamped = max(calibration.pulse_min, min(calibration.pulse_max, pulse_us))
        self._pca.channels[channel].duty_cycle = _pulse_us_to_duty(clamped)

    def disable(self, channel: int) -> None:
        self._guard_channel(channel)
        self._pca.channels[channel].duty_cycle = 0

    def disable_all(self) -> None:
        for ch in range(PCA9685_CHANNELS):
            self._pca.channels[ch].duty_cycle = 0

    def is_real_hardware(self) -> bool:
        return True

    @staticmethod
    def _guard_channel(channel: int) -> None:
        if not 0 <= channel < PCA9685_CHANNELS:
            raise ValueError(f"channel out of range: {channel}")


class SimulatorServoDriver:
    """In-memory driver that records commands for tests and laptop dev."""

    def __init__(self) -> None:
        self._pulses: dict[int, int] = {}

    def set_pulse(self, channel: int, pulse_us: int) -> None:
        self._guard_channel(channel)
        self._pulses[channel] = pulse_us

    def set_pulse_safe(
        self, channel: int, pulse_us: int, calibration: ChannelCalibration
    ) -> None:
        self._guard_channel(channel)
        clamped = max(calibration.pulse_min, min(calibration.pulse_max, pulse_us))
        self._pulses[channel] = clamped

    def disable(self, channel: int) -> None:
        self._guard_channel(channel)
        self._pulses.pop(channel, None)

    def disable_all(self) -> None:
        self._pulses.clear()

    def is_real_hardware(self) -> bool:
        return False

    def snapshot(self) -> dict[int, int]:
        """Return a copy of the current per-channel pulses (test helper)."""
        return dict(self._pulses)

    @staticmethod
    def _guard_channel(channel: int) -> None:
        if not 0 <= channel < PCA9685_CHANNELS:
            raise ValueError(f"channel out of range: {channel}")


def get_servo_driver() -> ServoDriver:
    """Return HardwareServoDriver if the I2C stack imports, else simulator.

    The hardware driver is constructed lazily inside the try block so an
    import failure (running on Windows, missing libs) falls cleanly through
    to the simulator without raising.
    """
    try:
        import board  # noqa: F401
        import busio  # noqa: F401
        from adafruit_pca9685 import PCA9685  # noqa: F401

        return HardwareServoDriver()
    except Exception:
        return SimulatorServoDriver()
