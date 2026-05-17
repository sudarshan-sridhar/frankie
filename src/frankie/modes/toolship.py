"""Toolship mode.

Operator asks for a fastener by name ("M6 bolt"); the arm picks the
matching tool and hands it over with a safety warning.

Primary pickup path is now vision: a colour signature from
``data/calibration/tools.json`` describes each screwdriver and the camera
finds it on the bench at runtime. Tools that ship without a colour fall
back to legacy hardcoded XYZ positions in the same JSON, so the operator
can still ask for M4/M5 from the tray.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import cv2
import numpy as np
import structlog
from pydantic import BaseModel, Field

from frankie.config import get_settings
from frankie.hardware.arm import DEFAULT_PICK_Z_MM, DEFAULT_TRANSIT_Z_MM
from frankie.modes.base import ModeResponse

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from frankie.hardware.arm import Arm
    from frankie.hardware.kinematics import Kinematics
    from frankie.vision.camera import Camera
    from frankie.vision.workspace import Workspace

log = structlog.get_logger(__name__)

# Match "M3", "M3 bolt", "give me M6", "M10 please" etc.
_TOOL_RE = re.compile(r"\bM\s*(\d{1,2})\b", re.IGNORECASE)

# After moving to the handoff position with the tool, wait this long before
# opening the gripper so the operator can grasp it.
HANDOFF_PAUSE_S = 2.0

# Pixel area floor for a candidate screwdriver contour. Smaller blobs are
# almost certainly shadows / specular highlights / wires. Loosened to 200
# because the demo screwdriver handles only show a thin coloured ring
# around a rubber grip — the total saturated area is small.
SCREWDRIVER_MIN_AREA_PX = 200

# HSV bands per colour name. Red wraps the hue circle so we union two
# windows. Bands tuned for the HackMI demo tools: bright primaries plus
# an all-purpose "black" band for dark rubber grips. Pixel-position
# filtering inside the marker rectangle keeps off-bench plastic from
# matching.
COLOR_HSV_BANDS: dict[str, tuple[tuple[tuple[int, int, int], tuple[int, int, int]], ...]] = {
    "red": (
        ((0, 100, 60), (10, 255, 255)),
        ((170, 100, 60), (180, 255, 255)),
    ),
    "blue": (
        ((95, 100, 60), (130, 255, 255)),
    ),
    "yellow": (
        ((18, 90, 90), (35, 255, 255)),
    ),
    "black": (
        # V_min=22 excludes the pure-black ArUco marker squares (V~0-15) so
        # they don't outrank a real screwdriver handle in the contour ranking.
        # V_max=70 still admits the rubber-grip handle.
        ((0, 0, 22), (180, 110, 70)),
    ),
}


class ToolEntry(BaseModel):
    """One row of tools.json. Either ``color`` (vision) or
    ``world_xyz_mm`` (legacy tray pickup) must be present.

    ``pick_z_mm`` overrides the default cube pick height for tools that sit
    lower on the bench (screwdrivers).
    """

    description: str
    warning: str
    color: str | None = None
    world_xyz_mm: tuple[float, float, float] | None = None
    pick_z_mm: float | None = None


class ToolsConfig(BaseModel):
    """Schema for data/calibration/tools.json."""

    version: int = 2
    # Outside-right of the workspace cardboard so the operator's hand is
    # clear of taught objects on the bench.
    handoff_xyz_mm: tuple[float, float, float] = Field(default=(60.0, 150.0, 80.0))
    tools: dict[str, ToolEntry]


def _default_tools_path() -> Path:
    return get_settings().calibration_dir / "tools.json"


def load_tools(path: Path | None = None) -> ToolsConfig:
    """Read and validate tools.json."""
    target = path or _default_tools_path()
    return ToolsConfig.model_validate_json(target.read_text(encoding="utf-8"))


def parse_tool_name(command: str) -> str | None:
    """Extract a tool key like 'M6' from a free-form command, or None."""
    match = _TOOL_RE.search(command)
    if match is None:
        return None
    return f"M{int(match.group(1))}"


def _color_mask(
    frame: NDArray[np.uint8], color: str
) -> NDArray[np.uint8] | None:
    """Union HSV mask for the requested colour, or None if unknown."""
    bands = COLOR_HSV_BANDS.get(color.lower())
    if bands is None:
        return None
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask: NDArray[np.uint8] | None = None
    for lo, hi in bands:
        band = cv2.inRange(hsv, np.array(lo, dtype=np.uint8), np.array(hi, dtype=np.uint8))
        mask = band if mask is None else cv2.bitwise_or(mask, band)
    assert mask is not None  # at least one band always present
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    return mask


def _find_grip_center_px(
    contour: NDArray[np.int32],
) -> tuple[float, float] | None:
    """Return the centroid of the coloured handle contour in pixel coords.

    We tried picking the "thicker half" of the contour first, but on
    cylindrical screwdriver handles every cross-slice has roughly the same
    width, so the half-width algorithm settled on the far rounded butt end
    — too close to the edge for the gripper to close around reliably.
    The contour centroid is the middle of the colored region, which is a
    stable, predictable grip point on a uniform handle.
    """
    rect = cv2.minAreaRect(contour)
    (cx, cy), (w, h), _angle_deg = rect
    if max(w, h) < 1.0:
        return None
    m = cv2.moments(contour)
    if m["m00"] > 0:
        return (float(m["m10"] / m["m00"]), float(m["m01"] / m["m00"]))
    return (float(cx), float(cy))


def _marker_pixel_bbox(workspace: Workspace) -> tuple[float, float, float, float] | None:
    """Inclusive pixel bounding box of the 4 calibration markers.

    Rejects two classes of false positives:
    - Contours OUTSIDE the workspace cardboard (power strips, cables, the
      back wall) that map to negative or out-of-range world coords.
    - The ArUco marker squares themselves — pure black blobs that would
      otherwise outrank a real screwdriver handle on the "black" band.

    Shrunk inward by 10 px so marker edges don't bleed into the accepted
    region, but not so aggressive that a screwdriver placed near a marker
    gets clipped out.
    """
    centers = workspace.calibration.marker_pixel_centers
    if not centers or len(centers) < 4:
        return None
    xs = [c[0] for c in centers.values()]
    ys = [c[1] for c in centers.values()]
    pad = -10.0
    return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)


def locate_screwdriver_grip(
    frame: NDArray[np.uint8],
    color: str,
    workspace: Workspace,
) -> tuple[float, float] | None:
    """Find the requested-colour screwdriver and return its grip in pixels.

    Two-stage filter: (1) contour centroid must lie inside the marker pixel
    bounding box (kills off-bench false positives like power strips), then
    (2) projected world coord must lie in the reachable world rectangle.
    """
    mask = _color_mask(frame, color)
    if mask is None:
        return None
    bbox = _marker_pixel_bbox(workspace)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates: list[tuple[float, NDArray[np.int32]]] = []
    for c in contours:
        area = float(cv2.contourArea(c))
        if area < SCREWDRIVER_MIN_AREA_PX:
            continue
        m = cv2.moments(c)
        if m["m00"] <= 0:
            continue
        cx = m["m10"] / m["m00"]
        cy = m["m01"] / m["m00"]
        if bbox is not None:
            xlo, ylo, xhi, yhi = bbox
            if not (xlo <= cx <= xhi and ylo <= cy <= yhi):
                continue
        world_xy = workspace.pixel_to_world((float(cx), float(cy)))
        if not workspace.is_in_reachable_region(world_xy):
            continue
        candidates.append((area, c))
    log.info(
        "toolship.locate",
        color=color,
        n_contours=len(contours),
        n_candidates=len(candidates),
        bbox=list(bbox) if bbox else None,
    )
    if not candidates:
        return None
    candidates.sort(key=lambda t: t[0], reverse=True)
    _, best = candidates[0]
    return _find_grip_center_px(best)


class ToolshipMode:
    """Tool-handover state machine."""

    name = "toolship"

    def __init__(
        self,
        arm: Arm,
        kinematics: Kinematics,
        camera: Camera | None = None,
        workspace: Workspace | None = None,
        tools: ToolsConfig | None = None,
    ) -> None:
        self._arm = arm
        self._ik = kinematics
        self._camera = camera
        self._workspace = workspace
        self._tools = tools or load_tools()
        self._active = False

    async def start(self) -> None:
        self._active = True
        log.info("toolship.start", tools=list(self._tools.tools.keys()))

    async def stop(self) -> None:
        self._active = False
        log.info("toolship.stop")

    async def _clear_view_for_snapshot(self) -> None:
        """Tuck the arm out of the workspace so vision has a clean shot."""
        try:
            await self._arm.jog_joint("shoulder", 55.0)
            await self._arm.jog_joint("base", 75.0)
        except Exception:
            log.exception("toolship.clear_view_failed")

    async def handle_command(
        self, command: str, context: dict[str, Any]
    ) -> ModeResponse:
        del context  # toolship is stateless
        if not self._active:
            return ModeResponse(
                spoken="Toolship is not running.",
                action_taken="rejected",
                next_state={"reason": "inactive"},
            )

        tool_key = parse_tool_name(command)
        if tool_key is None:
            return ModeResponse(
                spoken="I didn't catch the tool size. Say something like M6 or M4.",
                action_taken="parse_failed",
                next_state={"command": command},
            )

        entry = self._tools.tools.get(tool_key)
        if entry is None:
            available = ", ".join(sorted(self._tools.tools.keys()))
            return ModeResponse(
                spoken=f"I don't have a {tool_key}. I have {available}.",
                action_taken="unknown_tool",
                next_state={"requested": tool_key},
            )

        # Clear the arm out of the workspace before vision so the gripper
        # doesn't sit on top of the screwdriver we're trying to find.
        if entry.color is not None:
            await self._clear_view_for_snapshot()
            return await self._deliver_by_vision(tool_key, entry)
        if entry.world_xyz_mm is not None:
            return await self._deliver_by_position(tool_key, entry)
        return ModeResponse(
            spoken=f"I don't have a pickup recipe for {tool_key}.",
            action_taken="missing_recipe",
            next_state={"requested": tool_key},
        )

    async def _deliver_by_vision(
        self, tool_key: str, entry: ToolEntry
    ) -> ModeResponse:
        if self._camera is None or self._workspace is None:
            return ModeResponse(
                spoken=f"I can't use vision right now to find the {tool_key}.",
                action_taken="vision_unavailable",
                next_state={"requested": tool_key, "color": entry.color},
            )
        assert entry.color is not None  # narrowed by caller

        try:
            frame = await self._camera.snapshot()
        except TimeoutError:
            return ModeResponse(
                spoken="I can't see the camera right now.",
                action_taken="camera_timeout",
                next_state={"requested": tool_key},
            )

        grip_px = locate_screwdriver_grip(frame, entry.color, self._workspace)
        if grip_px is None:
            return ModeResponse(
                spoken=f"I can't see the {tool_key} anywhere on the bench.",
                action_taken="not_found",
                next_state={"requested": tool_key, "color": entry.color},
            )

        world_xy = self._workspace.pixel_to_world(grip_px)
        pick_z = entry.pick_z_mm if entry.pick_z_mm is not None else DEFAULT_PICK_Z_MM
        log.info(
            "toolship.deliver.vision",
            tool=tool_key,
            color=entry.color,
            grip_px=list(grip_px),
            world_xy=list(world_xy),
            pick_z_mm=pick_z,
        )
        await self._arm.pick_at(
            (float(world_xy[0]), float(world_xy[1])),
            self._ik,
            pick_z_mm=pick_z,
            transit_z_mm=DEFAULT_TRANSIT_Z_MM,
        )
        return await self._handoff(tool_key, entry, extra_state={
            "color": entry.color,
            "grip_px": [float(grip_px[0]), float(grip_px[1])],
            "world_xy": [float(world_xy[0]), float(world_xy[1])],
            "pick_z_mm": pick_z,
            "path": "vision",
        })

    async def _deliver_by_position(
        self, tool_key: str, entry: ToolEntry
    ) -> ModeResponse:
        assert entry.world_xyz_mm is not None
        log.info("toolship.deliver.position", tool=tool_key)
        tool_xy = (entry.world_xyz_mm[0], entry.world_xyz_mm[1])
        await self._arm.pick_at(
            tool_xy,
            self._ik,
            pick_z_mm=entry.world_xyz_mm[2],
            transit_z_mm=DEFAULT_TRANSIT_Z_MM,
        )
        return await self._handoff(tool_key, entry, extra_state={
            "tray_xyz_mm": list(entry.world_xyz_mm),
            "path": "position",
        })

    async def _handoff(
        self,
        tool_key: str,
        entry: ToolEntry,
        *,
        extra_state: dict[str, Any],
    ) -> ModeResponse:
        handoff = self._tools.handoff_xyz_mm
        # Traverse at safe transit height, then descend to the handoff drop.
        await self._arm.move_to_xyz(handoff[0], handoff[1], DEFAULT_TRANSIT_Z_MM, self._ik)
        await self._arm.move_to_xyz(handoff[0], handoff[1], handoff[2], self._ik)
        await asyncio.sleep(HANDOFF_PAUSE_S)
        await self._arm.gripper_open()
        spoken = f"Here is your {tool_key}, the {entry.description}. {entry.warning}"
        next_state: dict[str, Any] = {
            "tool": tool_key,
            "description": entry.description,
        }
        next_state.update(extra_state)
        return ModeResponse(
            spoken=spoken,
            action_taken=f"delivered:{tool_key}",
            next_state=next_state,
        )


__all__ = [
    "COLOR_HSV_BANDS",
    "HANDOFF_PAUSE_S",
    "SCREWDRIVER_MIN_AREA_PX",
    "ToolEntry",
    "ToolsConfig",
    "ToolshipMode",
    "load_tools",
    "locate_screwdriver_grip",
    "parse_tool_name",
]
