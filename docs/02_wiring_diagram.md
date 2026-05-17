# Wiring Diagram

## Pi 5 to PCA9685 (I2C control side)

```
Pi 5 (GPIO header)              PCA9685
+----------------+               +----------------+
| pin 1  (3V3)   |---red-------->| VCC            |
| pin 3  (SDA)   |---green------>| SDA            |
| pin 5  (SCL)   |---yellow----->| SCL            |
| pin 6  (GND)   |---black------>| GND            |
+----------------+               +----------------+
```

VCC carries the 3.3V logic supply only. The PCA9685's servo rail is
separate and lives on V+ / GND on the screw terminals.

## PCA9685 servo rail

```
SoulBay UC22U-SB @ 6V, 4A max
+----------+
|   +6V    |---->  PCA9685 V+ (screw terminal)
|   GND    |---->  PCA9685 GND (screw terminal)
+----------+
                   (common ground with the Pi)
```

POWER LED on the PCA9685 must be lit before any servo movement is
commanded. If the LED is off, V+ is not seated.

## Servo channel layout (from the V+ terminal side, left to right)

```
PCA9685 PWM headers
+----+----+----+----+----+
|  0 |  1 |  2 |  3 |  4 |
+----+----+----+----+----+
  GR   WR   EL   SH   BA
```

GR = gripper (LFD-01M), WR = wrist (LFD-01M), EL = elbow (LFD-01M),
SH = shoulder (LDX-218), BA = base (LD-1501MG).

Each servo header is the standard 3-pin: signal (yellow/white), V+ (red),
GND (brown/black). Match orientation: V+ to the V+ rail.
