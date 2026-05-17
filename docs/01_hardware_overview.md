# Hardware Overview

## Servo channel map (PCA9685 at 0x40, bus 1)

| Channel | Servo | Voltage | Stall current | Joint |
|---|---|---|---|---|
| 0 | LFD-01M | 4.8-6V | 700mA | Gripper |
| 1 | LFD-01M | 4.8-6V | 700mA | Wrist |
| 2 | LFD-01M | 4.8-6V | 700mA | Elbow |
| 3 | LDX-218 | 6-7.4V | ~2.5A peak | Shoulder |
| 4 | LD-1501MG | 6-7.4V | ~3A peak | Base |

Channel numbering is read from the V+ terminal side of the PCA9685.

## Power

Single 6V rail to V+ from SoulBay UC22U-SB universal adapter set at 6V, 4A
max. Pi 5 runs from its own 5V USB-C supply. Common ground at the PCA9685.

Backup: a 7.4V 2S 18650 pack for short bench tests only. Do not leave the
LFD-01M servos on 7.4V for extended runs.

## Pi 5 credentials

- Hostname: `UMDCLAW.local`
- IP: `192.168.1.102`
- Username: `rpclaw`
- Password: `piclaw`
- SSH target: `rpclaw@UMDCLAW.local`
- SSH key auth set up; no password prompts in normal development.
- I2C enabled, PCA9685 confirmed at 0x40 on bus 1.

## Camera

Phone running DroidCam (Android) or Iriun (iOS) streaming MJPEG over Wi-Fi.
Typical URL: `http://192.168.x.x:4747/video`.

## Workspace

White surface 40x30 cm, arm clamped at center of the back edge facing
forward. Coordinate frame:

- Origin (0, 0, 0) at base center, table surface
- X forward (toward operator)
- Y left/right (left negative, right positive)
- Z up

Reachable region: X in [80, 230] mm, Y in [-180, 180] mm, Z in [0, 200] mm.
