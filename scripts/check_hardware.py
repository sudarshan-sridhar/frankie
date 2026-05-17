"""Probe I2C and confirm PCA9685 presence on the Pi.

Phase 1 ships a minimal smoke check. Phase 2 expands it to read back the
PCA9685 prescaler and ping each servo with a centering pulse.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    """Print I2C bus status and PCA9685 detection result. Returns 0 on success."""
    bus_path = Path("/dev/i2c-1")
    print(f"i2c-1 present: {bus_path.exists()}")
    try:
        from smbus2 import SMBus  # type: ignore[import-not-found]
    except ImportError:
        print("smbus2 not installed; install with: uv pip install smbus2")
        return 1
    detected: list[int] = []
    try:
        with SMBus(1) as bus:
            for addr in range(0x03, 0x78):
                try:
                    bus.read_byte(addr)
                    detected.append(addr)
                except OSError:
                    pass
    except FileNotFoundError:
        print("No /dev/i2c-1. Enable I2C via raspi-config and reboot.")
        return 1
    print(f"detected addresses: {[hex(a) for a in detected]}")
    if 0x40 in detected:
        print("PCA9685 detected at 0x40. Confirm POWER LED is on.")
        return 0
    print("PCA9685 NOT detected at 0x40. Check wiring and 6V rail.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
