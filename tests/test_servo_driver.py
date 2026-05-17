"""Simulator driver smoke tests + pulse-to-duty math.

The hardware driver is exercised on the Pi via the live API; here we
verify the bits that run on any platform.
"""

from __future__ import annotations

import pytest

from frankie.hardware.calibration import default_calibration
from frankie.hardware.servo_driver import (
    PCA9685_CHANNELS,
    SimulatorServoDriver,
    _pulse_us_to_duty,
    get_servo_driver,
)


def test_simulator_records_pulses() -> None:
    drv = SimulatorServoDriver()
    drv.set_pulse(3, 1500)
    drv.set_pulse(4, 1200)
    assert drv.snapshot() == {3: 1500, 4: 1200}
    drv.disable(3)
    assert drv.snapshot() == {4: 1200}
    drv.disable_all()
    assert drv.snapshot() == {}
    assert drv.is_real_hardware() is False


def test_factory_returns_a_valid_driver() -> None:
    drv = get_servo_driver()
    # On Windows/Linux laptops -> simulator. On the Pi -> HardwareServoDriver.
    # Either way, it must satisfy the Protocol.
    assert hasattr(drv, "set_pulse")
    assert hasattr(drv, "disable_all")
    assert isinstance(drv.is_real_hardware(), bool)


def test_set_pulse_safe_clamps_to_calibration_bounds() -> None:
    drv = SimulatorServoDriver()
    cal = default_calibration().get(3)  # shoulder: pulse 500..2500
    drv.set_pulse_safe(3, 100, cal)
    assert drv.snapshot()[3] == 500
    drv.set_pulse_safe(3, 9000, cal)
    assert drv.snapshot()[3] == 2500


def test_channel_out_of_range_raises() -> None:
    drv = SimulatorServoDriver()
    with pytest.raises(ValueError):
        drv.set_pulse(PCA9685_CHANNELS, 1500)
    with pytest.raises(ValueError):
        drv.set_pulse(-1, 1500)


def test_pulse_us_to_duty_math() -> None:
    # 50Hz period = 20000us. 1500us pulse -> 1500/20000 * 65535 = 4915
    assert _pulse_us_to_duty(0) == 0
    assert _pulse_us_to_duty(-100) == 0
    assert 4900 <= _pulse_us_to_duty(1500) <= 4920
    # full period
    assert _pulse_us_to_duty(20000) == 65535
    # over-period clamps
    assert _pulse_us_to_duty(30000) == 65535
