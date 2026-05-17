"""Run IK for the exact clicked targets and report joint angles + FK + gripper direction."""

from __future__ import annotations

import numpy as np

from frankie.hardware.kinematics import DHParameters, Kinematics


def main() -> int:
    dh = DHParameters.load()
    ik = Kinematics(dh)

    targets = {
        "click@ID1 (30.1, 129.0)":    (30.1, 129.0, 30.0),
        "click@ID2 (151.5, 125.4)":   (151.5, 125.4, 30.0),
        "click@ID3 (146.5, -121.3)":  (146.5, -121.3, 30.0),
    }

    for label, target in targets.items():
        print(f"=== {label} ===")
        angles = ik.inverse(target, initial_angles_deg=None)
        fk = ik.forward(angles)
        err = ((fk[0] - target[0]) ** 2 + (fk[1] - target[1]) ** 2 + (fk[2] - target[2]) ** 2) ** 0.5
        print(f"  angles: base={angles['base']:+6.1f} shoulder={angles['shoulder']:+6.1f} "
              f"elbow={angles['elbow']:+6.1f} wrist={angles['wrist']:+6.1f}")
        print(f"  FK fingertip: ({fk[0]:+7.1f}, {fk[1]:+7.1f}, {fk[2]:+7.1f})  err={err:.1f} mm")
        # Compute approximate wrist position (before L3)
        # Use forward kinematics with wrist link removed: compute angle sums
        import math
        s = math.radians(angles['shoulder'])
        e = math.radians(angles['elbow'])
        w = math.radians(angles['wrist'])
        b = math.radians(angles['base'])
        # In our chain w/ origin_orientation [0,-pi/2,0], shoulder=0 means up
        # Each rotation around Y adds to the in-plane angle
        # Direction of upper arm (from shoulder) in local plane:
        # at shoulder=0: vertical up.  shoulder rotation rotates this direction.
        # Approximate gripper direction = cumulative rotation around Y starting from +Z (up)
        total_y_rot = s + e + w  # total rotation from +Z (up)
        # gripper x-axis direction (in plane): from +Z rotated by total_y_rot around +Y
        # +Z rotated by theta around +Y: (sin(theta), 0, cos(theta))
        gx_local = (math.sin(total_y_rot), 0, math.cos(total_y_rot))
        # Then rotate by base around +Z
        gx_world = (
            gx_local[0] * math.cos(b) - gx_local[1] * math.sin(b),
            gx_local[0] * math.sin(b) + gx_local[1] * math.cos(b),
            gx_local[2],
        )
        # The "down" direction is (0, 0, -1). dot product = how aligned gripper is with down
        down_alignment = -gx_world[2]  # 1 = fully down, 0 = horizontal, -1 = up
        print(f"  gripper dir (world): ({gx_world[0]:+.2f}, {gx_world[1]:+.2f}, {gx_world[2]:+.2f})")
        print(f"  alignment with DOWN: {down_alignment:+.2f}  "
              f"({'GOOD' if down_alignment > 0.7 else 'SIDEWAYS' if abs(down_alignment) < 0.3 else 'OK'})")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
