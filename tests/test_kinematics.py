"""Forward/inverse kinematics: round-trip + reach check."""

from __future__ import annotations

from frankie.hardware.kinematics import DHParameters, Kinematics


def test_dh_parameters_construct() -> None:
    dh = DHParameters(50, 80, 80, 40)
    assert dh.L1_shoulder_to_elbow == 80


def test_forward_zero_angles_gives_max_reach_along_x() -> None:
    dh = DHParameters(50, 80, 80, 40)
    ik = Kinematics(dh)
    xyz = ik.forward({"base": 0, "shoulder": 0, "elbow": 0, "wrist": 0})
    # With all joints at 0 the chain is shoulder-up + arm horizontal +X.
    # x should be ~ L1+L2+L3 = 200mm; y ~ 0; z ~ L0.
    assert abs(xyz[0] - 200) < 1.0
    assert abs(xyz[1]) < 1.0
    assert abs(xyz[2] - 50) < 1.0


def test_inverse_round_trip_near_neutral() -> None:
    dh = DHParameters(50, 80, 80, 40)
    ik = Kinematics(dh)
    target = (150.0, 0.0, 60.0)
    assert ik.is_reachable(target)
    angles = ik.inverse(target)
    xyz_back = ik.forward(angles)
    assert abs(xyz_back[0] - target[0]) < 8.0
    assert abs(xyz_back[1] - target[1]) < 8.0
    assert abs(xyz_back[2] - target[2]) < 8.0


def test_unreachable_far() -> None:
    dh = DHParameters(50, 80, 80, 40)
    ik = Kinematics(dh)
    assert not ik.is_reachable((600.0, 0.0, 0.0))
