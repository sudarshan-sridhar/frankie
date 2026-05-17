# Servo Calibration Guide

Run this once when the arm is built. The output is `data/calibration/servos.json`,
which every subsequent run reads.

## Before you start

1. Mount the arm at the back edge of the workspace, facing forward.
2. **Power off** the SoulBay 6V rail. The servo wires must be cold during
   the first read of pulse_center so a bad value can't slam a joint into
   its hard stop.
3. Set the SoulBay output dial to 6V. Confirm the polarity (red to PCA9685
   V+, black to GND).
4. Plug the SoulBay barrel jack into the V+/GND screw terminals on the
   PCA9685. Do not power it yet.

## Power on, in this order

1. `ssh rpclaw@UMDCLAW.local` and confirm `systemctl status frankie`
   reports `active (running)`. (The service holds the I2C bus already.)
2. On the Pi, stop the service so the calibration script can claim the bus:
   `sudo systemctl stop frankie`
3. Power on the SoulBay. The red **POWER LED** on the PCA9685 lights up.
   The arm should still be limp; the PCA9685 is not driving any channel yet.

## Run the script

Run from the laptop:

```
make calibrate-servos
```

This SSHes into the Pi with `-t` (interactive TTY) and runs
`scripts/calibrate_servos.py`. You'll walk every channel in this order:

| Step | Channel | Joint | Servo |
|---|---|---|---|
| 1 | 0 | gripper | LFD-01M |
| 2 | 1 | wrist | LFD-01M |
| 3 | 2 | elbow | LFD-01M |
| 4 | 3 | shoulder | LDX-218 |
| 5 | 4 | base | LD-1501MG |

### Per-channel procedure

For each joint:

1. Script starts at the default `pulse_center` (typically 1500us). The
   servo should snap to roughly the middle of its travel. If it slams
   into a stop, hit Ctrl+C and adjust the default in
   `default_calibration()` before retrying.
2. Tap **left/right arrow** for fine adjustments (5us per tap).
3. Tap **up/down arrow** for coarse adjustments (50us; script sleeps
   200ms to let the servo settle).
4. When the joint just touches its physical lower stop without straining,
   press `m` to mark `pulse_min`.
5. Move to the upper stop, press `M` for `pulse_max`.
6. Move to the neutral pose (joints aligned, arm pointing forward and up
   in the home configuration), press `c` for `pulse_center`.
7. For the **gripper only**: open the jaws fully, press `o` for
   `pulse_open`. Close them gently against each other (no part in the
   gripper), press `C` (capital) for `pulse_closed`.
8. If commanding "increase" moves the joint the wrong direction, press
   `i` to toggle inversion and reverify min/max.
9. Press `n` to advance to the next channel. The script saves after
   every channel.

### Hotkeys

| Key | Action |
|---|---|
| ← / → | -5us / +5us |
| ↑ / ↓ | +50us / -50us (200ms settle) |
| m / M | mark pulse_min / pulse_max |
| c | mark pulse_center |
| i | toggle inversion |
| o / C | (gripper only) mark pulse_open / pulse_closed |
| n / p | next / previous channel (saves first) |
| s | save and continue |
| q | save and quit |

## After calibration

1. Power down the SoulBay.
2. Restart the service: `sudo systemctl start frankie`
3. From the laptop, open `http://UMDCLAW.local:8000`. Try a slider; the
   live arm pose should follow. With the rail still off, you'll see the
   readouts move but the physical joints stay still.
4. When you're confident, power the rail back up and try the sliders
   again. The joints should track the sliders in real time.

## Recovery: I ran a value too aggressive and a servo is straining

Press **E-STOP** in the browser. The frontend calls `/api/estop` which
cuts duty cycle on every channel; the servos go limp immediately. Power
the rail down at the SoulBay if the servos buzz.

Then either:
- Manually edit `data/calibration/servos.json` to widen the offending
  channel, or
- Re-run `make calibrate-servos` and walk that channel again.
