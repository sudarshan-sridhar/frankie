"""Forward and inverse kinematics for the 5-DOF arm via ikpy.

The chain is base (Z rotation) -> shoulder (Y rotation) -> elbow (Y) ->
wrist (Y) -> gripper TCP. Link lengths come from
data/calibration/arm_dh.json (written by scripts/measure_arm.py).

inverse(target_xyz) returns angles in degrees keyed by joint name so
callers stay link-name agnostic. Forward solves the reverse for sanity
checks.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

import numpy as np
import structlog
from ikpy.chain import Chain
from ikpy.link import OriginLink, URDFLink

from frankie.config import get_settings

log = structlog.get_logger(__name__)


JOINT_ORDER: tuple[str, ...] = ("base", "shoulder", "elbow", "wrist")


@dataclass
class DHParameters:
    """Link lengths in mm between joint pivots and fingertip."""

    L0_base_to_shoulder: float
    L1_shoulder_to_elbow: float
    L2_elbow_to_wrist: float
    L3_wrist_to_gripper: float

    @classmethod
    def load(cls) -> DHParameters:
        path = get_settings().calibration_dir / "arm_dh.json"
        if not path.exists():
            raise FileNotFoundError(
                f"{path} not found. run scripts/measure_arm.py first."
            )
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            L0_base_to_shoulder=raw["L0_base_to_shoulder"],
            L1_shoulder_to_elbow=raw["L1_shoulder_to_elbow"],
            L2_elbow_to_wrist=raw["L2_elbow_to_wrist"],
            L3_wrist_to_gripper=raw["L3_wrist_to_gripper"],
        )


def _build_chain(dh: DHParameters) -> Chain:
    """ikpy expects metres. Convert mm -> m on construction."""
    mm = 1.0 / 1000.0
    return Chain(
        name="claw",
        links=[
            OriginLink(),
            URDFLink(
                name="base",
                origin_translation=[0, 0, dh.L0_base_to_shoulder * mm],
                origin_orientation=[0, 0, 0],
                rotation=[0, 0, 1],
                bounds=(-math.pi / 2, math.pi / 2),
            ),
            URDFLink(
                name="shoulder",
                origin_translation=[0, 0, 0],
                origin_orientation=[0, -math.pi / 2, 0],
                rotation=[0, 1, 0],
                bounds=(-math.pi / 2, math.pi / 2),
            ),
            URDFLink(
                name="elbow",
                origin_translation=[dh.L1_shoulder_to_elbow * mm, 0, 0],
                origin_orientation=[0, 0, 0],
                rotation=[0, 1, 0],
                bounds=(-math.pi / 2, math.pi / 2),
            ),
            URDFLink(
                name="wrist",
                origin_translation=[dh.L2_elbow_to_wrist * mm, 0, 0],
                origin_orientation=[0, 0, 0],
                rotation=[0, 1, 0],
                bounds=(-math.pi / 2, math.pi / 2),
            ),
            URDFLink(
                name="tcp",
                origin_translation=[dh.L3_wrist_to_gripper * mm, 0, 0],
                origin_orientation=[0, 0, 0],
                joint_type="fixed",
            ),
        ],
        active_links_mask=[False, True, True, True, True, False],
    )


class Kinematics:
    """ikpy-backed solver bound to a fixed DHParameters instance."""

    def __init__(self, dh: DHParameters) -> None:
        self._dh = dh
        self._chain = _build_chain(dh)
        # Reach (mm) measured shoulder horizontal arm extended fully.
        self._max_reach_mm = dh.L1_shoulder_to_elbow + dh.L2_elbow_to_wrist + dh.L3_wrist_to_gripper
        self._min_reach_mm = max(
            0.0,
            abs(dh.L1_shoulder_to_elbow - dh.L2_elbow_to_wrist - dh.L3_wrist_to_gripper),
        )

    @property
    def dh(self) -> DHParameters:
        return self._dh

    def inverse(
        self,
        target_xyz: tuple[float, float, float],
        initial_angles_deg: dict[str, float] | None = None,
    ) -> dict[str, float]:
        """Solve for joint angles (deg) reaching target_xyz in mm world frame.

        Constrains the gripper TCP X-axis to point along world -Z (gripper down)
        so the arm produces a natural "reach toward the table" pose. Seeds the
        solver with ``initial_angles_deg`` if provided so consecutive calls are
        deterministic and minimise joint movement.
        """
        target_m = np.asarray(target_xyz, dtype=np.float64) / 1000.0
        # Seed with a forward-down bias so the solver consistently picks
        # poses where the arm reaches forward+down rather than back+up.
        default_seed_deg = {"base": 0.0, "shoulder": 45.0, "elbow": 45.0, "wrist": 45.0}
        seed = default_seed_deg if initial_angles_deg is None else initial_angles_deg
        initial_position = np.array(
            [
                0.0,
                math.radians(seed.get("base", 0.0)),
                math.radians(seed.get("shoulder", 45.0)),
                math.radians(seed.get("elbow", 45.0)),
                math.radians(seed.get("wrist", 45.0)),
                0.0,
            ],
            dtype=np.float64,
        )

        # First try with gripper-down orientation. If the position error
        # becomes large (target is too far for orientation+position to both
        # be satisfied), fall back to position-only.
        angles_with_orient = self._chain.inverse_kinematics(
            target_m,
            target_orientation=np.array([0.0, 0.0, -1.0]),
            orientation_mode="X",
            initial_position=initial_position,
        )
        fk_with = self._chain.forward_kinematics(angles_with_orient)
        err_with_m = float(np.linalg.norm(fk_with[:3, 3] - target_m))
        if err_with_m * 1000.0 <= 10.0:
            angles_rad = angles_with_orient
        else:
            angles_rad = self._chain.inverse_kinematics(
                target_m,
                initial_position=initial_position,
            )
        # angles_rad[0] is OriginLink (always 0), last is TCP (fixed); map the
        # middle four to joint names.
        return {
            "base": math.degrees(angles_rad[1]),
            "shoulder": math.degrees(angles_rad[2]),
            "elbow": math.degrees(angles_rad[3]),
            "wrist": math.degrees(angles_rad[4]),
        }

    def forward(self, joint_angles: dict[str, float]) -> tuple[float, float, float]:
        """Compute fingertip XYZ (mm) from joint angles (deg)."""
        angles_rad = [
            0.0,
            math.radians(joint_angles.get("base", 0.0)),
            math.radians(joint_angles.get("shoulder", 0.0)),
            math.radians(joint_angles.get("elbow", 0.0)),
            math.radians(joint_angles.get("wrist", 0.0)),
            0.0,
        ]
        fk = self._chain.forward_kinematics(angles_rad)
        xyz_m = fk[:3, 3]
        return (float(xyz_m[0] * 1000), float(xyz_m[1] * 1000), float(xyz_m[2] * 1000))

    def is_reachable(self, target_xyz: tuple[float, float, float]) -> bool:
        """Cheap pre-check before calling inverse.

        Approximates the workspace as a hollow hemisphere of inner radius
        self._min_reach_mm and outer self._max_reach_mm around the
        shoulder pivot.
        """
        x, y, z = target_xyz
        # shoulder pivot is at (0, 0, L0)
        dz = z - self._dh.L0_base_to_shoulder
        r = math.sqrt(x * x + y * y + dz * dz)
        return self._min_reach_mm <= r <= self._max_reach_mm
