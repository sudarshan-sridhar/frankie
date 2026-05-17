"""Run IK for each marker target and print computed angles + FK round-trip."""

from __future__ import annotations

from frankie.hardware.kinematics import DHParameters, Kinematics


def main() -> int:
    dh = DHParameters.load()
    ik = Kinematics(dh)
    print(f"DH: L0={dh.L0_base_to_shoulder} L1={dh.L1_shoulder_to_elbow} "
          f"L2={dh.L2_elbow_to_wrist} L3={dh.L3_wrist_to_gripper}")
    print(f"max_reach={ik._max_reach_mm}mm  shoulder_at=(0,0,{dh.L0_base_to_shoulder})\n")

    targets = {
        "ID 0 (front-left)":  (30.0, -130.0, 30.0),
        "ID 1 (front-right)": (30.0, +130.0, 30.0),
        "ID 2 (back-right)":  (150.0, +130.0, 30.0),
        "ID 3 (back-left)":   (150.0, -130.0, 30.0),
        "Center":             (90.0, 0.0, 30.0),
    }
    seeds = {
        "from home":    {"base": 0.0, "shoulder": 0.0, "elbow": 0.0, "wrist": 0.0},
    }

    for label, target in targets.items():
        print(f"=== TARGET {label} {target} ===")
        for seed_label, seed in seeds.items():
            try:
                angles = ik.inverse(target, initial_angles_deg=seed)
            except Exception as exc:
                print(f"  {seed_label}: IK FAILED: {exc}")
                continue
            actual = ik.forward(angles)
            dx = actual[0] - target[0]
            dy = actual[1] - target[1]
            dz = actual[2] - target[2]
            err = (dx * dx + dy * dy + dz * dz) ** 0.5
            print(f"  {seed_label}: ", end="")
            print(f"base={angles['base']:+6.1f}  shoulder={angles['shoulder']:+6.1f}  "
                  f"elbow={angles['elbow']:+6.1f}  wrist={angles['wrist']:+6.1f}")
            print(f"  FK -> ({actual[0]:+7.1f}, {actual[1]:+7.1f}, {actual[2]:+7.1f})  "
                  f"err = {err:.1f} mm")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
