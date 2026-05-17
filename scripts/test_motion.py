"""Standalone motion REPL.

Loads calibration, constructs an Arm, and drops the user into asyncio.run
loops they can compose at will. Useful for sanity-checking a specific
joint without running the full FastAPI stack.

Run on the Pi:  uv run python scripts/test_motion.py
"""

from __future__ import annotations

import asyncio
import sys

from frankie.hardware.arm import Arm
from frankie.hardware.calibration import load_calibration
from frankie.hardware.servo_driver import get_servo_driver
from frankie.logging_config import configure_logging


async def _interactive(arm: Arm) -> None:
    print("\nclaw-companion REPL")
    print("  commands:  home | jog <joint> <deg> | open | close | grip <0..1> | estop | quit")
    print()
    loop = asyncio.get_event_loop()
    while True:
        line = await loop.run_in_executor(None, input, "claw> ")
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        cmd = parts[0].lower()
        try:
            if cmd in ("quit", "exit", "q"):
                break
            if cmd == "home":
                await arm.home()
            elif cmd == "jog" and len(parts) == 3:
                await arm.jog_joint(parts[1], float(parts[2]))
            elif cmd == "open":
                await arm.gripper_open()
            elif cmd == "close":
                await arm.gripper_close()
            elif cmd == "grip" and len(parts) == 2:
                await arm.gripper_set(float(parts[1]))
            elif cmd == "estop":
                await arm.emergency_stop()
            elif cmd == "clear":
                arm.clear_estop()
            elif cmd == "state":
                print(arm.get_state().model_dump_json(indent=2))
            else:
                print(f"unknown command: {line}")
        except Exception as exc:
            print(f"error: {exc}")


def main() -> int:
    configure_logging()
    driver = get_servo_driver()
    cal = load_calibration()
    mode = "hardware" if driver.is_real_hardware() else "simulator"
    print(f"mode={mode}")
    arm = Arm(driver, cal, mode=mode)
    try:
        asyncio.run(_interactive(arm))
    finally:
        driver.disable_all()
    return 0


if __name__ == "__main__":
    sys.exit(main())
