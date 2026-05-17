"""Interactive servo calibration CLI.

Runs on the Pi (`make calibrate-servos`). Walks channels 0..4 in fixed
order: gripper, wrist, elbow, shoulder, base. Use the arrow keys to nudge
the pulse, then mark min/center/max (and open/closed for the gripper).
JSON is saved after every channel so a Ctrl+C never wastes work.

Safety:
- First command per channel is the calibrated pulse_center (default 1500us).
- Each keystroke moves pulse by at most 50us; a 200ms gate runs after every
  larger jump.
- On Ctrl+C the script calls disable_all() so the arm goes limp.
"""

from __future__ import annotations

import sys
import time

from frankie.hardware.calibration import (
    CalibrationData,
    ChannelCalibration,
    GripperCalibration,
    JointCalibration,
    default_calibration,
    load_calibration,
    save_calibration,
)
from frankie.hardware.servo_driver import (
    PCA9685_CHANNELS,
    ServoDriver,
    get_servo_driver,
)

try:
    import readchar
except ImportError:
    readchar = None  # type: ignore[assignment]


CHANNEL_ORDER: list[int] = [0, 1, 2, 3, 4]

STEP_SMALL_US = 5
STEP_LARGE_US = 50
LARGE_STEP_SETTLE_S = 0.2


def _print_help(entry: ChannelCalibration, pulse: int) -> None:
    print()
    print(f"  channel={entry.name!r}  servo={entry.servo}")
    print(f"  pulse_min={entry.pulse_min}  pulse_center={entry.pulse_center}  pulse_max={entry.pulse_max}")
    if isinstance(entry, GripperCalibration):
        print(f"  pulse_open={entry.pulse_open}  pulse_closed={entry.pulse_closed}")
    print(f"  current pulse: {pulse}us  (inverted={entry.inverted})")
    print()
    print("  controls:")
    print("    Left/Right    nudge -/+ 5us")
    print("    Up/Down       nudge -/+ 50us (200ms settle)")
    print("    m / M         mark pulse_min / pulse_max")
    print("    c             mark pulse_center")
    print("    i             toggle inversion")
    if isinstance(entry, GripperCalibration):
        print("    o / C         mark pulse_open / pulse_closed")
    print("    n / p         next / previous channel (saves first)")
    print("    s             save and continue")
    print("    q             save and quit")
    print()


def _arrow(key: str) -> str | None:
    """Map raw readchar bytes to a logical direction name."""
    if key in ("\x1b[D", "\x00K", "\xe0K"):
        return "left"
    if key in ("\x1b[C", "\x00M", "\xe0M"):
        return "right"
    if key in ("\x1b[A", "\x00H", "\xe0H"):
        return "up"
    if key in ("\x1b[B", "\x00P", "\xe0P"):
        return "down"
    return None


def _calibrate_channel(
    driver: ServoDriver,
    cal: CalibrationData,
    channel: int,
) -> str:
    """Calibrate one channel. Returns 'next' | 'prev' | 'save' | 'quit'."""
    if readchar is None:
        raise RuntimeError("readchar not installed; pip install readchar")

    entry = cal.get(channel)
    pulse = entry.pulse_center

    # First command goes to the calibrated center: safe starting position.
    driver.set_pulse_safe(channel, pulse, entry)
    time.sleep(LARGE_STEP_SETTLE_S)

    _print_help(entry, pulse)

    while True:
        key = readchar.readkey()
        action = _arrow(key)
        delta = 0
        large = False

        if action == "left":
            delta = -STEP_SMALL_US
        elif action == "right":
            delta = STEP_SMALL_US
        elif action == "up":
            delta = STEP_LARGE_US
            large = True
        elif action == "down":
            delta = -STEP_LARGE_US
            large = True
        elif key == "m":
            entry.pulse_min = pulse
            print(f"  set pulse_min={pulse}")
        elif key == "M":
            entry.pulse_max = pulse
            print(f"  set pulse_max={pulse}")
        elif key == "c":
            entry.pulse_center = pulse
            print(f"  set pulse_center={pulse}")
        elif key == "i":
            entry.inverted = not entry.inverted
            print(f"  inverted={entry.inverted}")
        elif key == "o" and isinstance(entry, GripperCalibration):
            entry.pulse_open = pulse
            print(f"  set pulse_open={pulse}")
        elif key == "C" and isinstance(entry, GripperCalibration):
            entry.pulse_closed = pulse
            print(f"  set pulse_closed={pulse}")
        elif key == "n":
            return "next"
        elif key == "p":
            return "prev"
        elif key == "s":
            return "save"
        elif key in ("q", "Q", "\x03"):
            return "quit"
        else:
            continue

        if delta:
            pulse = max(entry.pulse_min, min(entry.pulse_max, pulse + delta))
            driver.set_pulse_safe(channel, pulse, entry)
            if large:
                time.sleep(LARGE_STEP_SETTLE_S)
            print(f"  pulse={pulse}us")


def _summary(cal: CalibrationData) -> None:
    print()
    print("calibration summary:")
    for ch_str, entry in cal.channels.items():
        bits = [f"min={entry.pulse_min}", f"center={entry.pulse_center}", f"max={entry.pulse_max}"]
        if isinstance(entry, GripperCalibration):
            bits += [f"open={entry.pulse_open}", f"closed={entry.pulse_closed}"]
        elif isinstance(entry, JointCalibration):
            bits += [f"angle_min={entry.angle_min_deg}", f"angle_max={entry.angle_max_deg}"]
        bits += [f"inverted={entry.inverted}"]
        print(f"  ch{ch_str} {entry.name:<10s} {entry.servo:<11s} " + "  ".join(bits))
    print()


def main() -> int:
    """Entry point: walks every channel, saves after each, gracefully exits."""
    driver = get_servo_driver()
    if not driver.is_real_hardware():
        print("WARNING: simulator driver in use; commands won't move physical servos.")
    cal = load_calibration()
    # If the loaded calibration is missing any expected channel, fill from defaults.
    defaults = default_calibration()
    for ch_str, entry in defaults.channels.items():
        cal.channels.setdefault(ch_str, entry)

    try:
        idx = 0
        while 0 <= idx < len(CHANNEL_ORDER):
            ch = CHANNEL_ORDER[idx]
            if ch >= PCA9685_CHANNELS:
                print(f"channel {ch} out of range; skipping")
                idx += 1
                continue
            print(f"\n=== channel {ch} ({cal.get(ch).name}) ===")
            action = _calibrate_channel(driver, cal, ch)
            driver.disable(ch)
            save_calibration(cal)
            if action == "quit":
                break
            if action == "prev":
                idx = max(0, idx - 1)
            else:
                idx += 1
    except KeyboardInterrupt:
        print("\n^C received; disabling all channels")
    finally:
        driver.disable_all()
        save_calibration(cal)

    _summary(cal)
    print("saved to data/calibration/servos.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
