"""Defect inspector mode.

States: IDLE -> READY (after start). Each command runs a phase
(TEACHING or INSPECTING) and returns to READY. Teach captures one object,
asks Claude Vision to describe its defect, stores image + ORB blob in the
defect KB. Inspect detects multiple objects, finds which one best matches a
previously taught defect, picks it up and drops it in a designated basket.

Object class is now free-form ("cube", "screwdriver", "bottle cap", ...).
The trailing token of a teach command becomes the class; commands that omit
a class fall back to ``"object"`` and the inspector queries every class
that has at least one taught defect.
"""

from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING, Any

import cv2
import structlog
from pydantic import BaseModel

from frankie.config import get_settings
from frankie.modes.base import ModeResponse
from frankie.reasoning import defect_kb
from frankie.vision import features

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

    from frankie.hardware.arm import Arm
    from frankie.hardware.kinematics import Kinematics
    from frankie.reasoning.router import ReasoningRouter
    from frankie.vision.camera import Camera
    from frankie.vision.workspace import Workspace

log = structlog.get_logger(__name__)

# Drop the defective object OUTSIDE the workspace grid, off to the left of
# the cardboard so a fresh inspect pass doesn't see it again. Tuned to stay
# inside the arm's 220 mm reach circle.
DEFAULT_BASKET_WORLD_XY: tuple[float, float] = (60.0, -150.0)
# Lift the carried object this high during traversal so it clears any
# remaining cubes still on the bench.
DEFECT_TRANSIT_Z_MM: float = 90.0
# Final drop height for the reject zone. Low enough that the cube doesn't
# bounce on release.
DEFECT_PLACE_Z_MM: float = 25.0

# HSV mask + contour area bounds for colored objects on a white cardboard.
# A 3 cm cube at the workspace fills ~80-150 px; widen the area window to
# absorb perspective + colour + shape variance (screwdrivers, caps, ...).
OBJECT_AREA_MIN_PX = 800
OBJECT_AREA_MAX_PX = 30000
HSV_SAT_MIN = 80
HSV_VAL_MIN = 60

# Below this weighted HSV distance two objects are the "same" colour. Tuned
# for OpenCV HSV (H in [0,180]); blue vs green = ~60 hue units, same-colour
# = usually < 15. Adjust if false positives.
COLOR_MATCH_DISTANCE_MAX = 25.0

DEFAULT_OBJECT_CLASS = "object"

DESCRIBE_PROMPT = (
    "You are inspecting a manufactured part. Describe any visible defect "
    "(scratches, dents, color smudges, broken edges) in 1-2 short sentences. "
    "If there is no visible defect, reply exactly 'no defect detected'."
)

# Commands the mode recognises. Two surfaces:
#
# TEACH — the explicit form ("teach defect <reason>") and the natural form
# ("this/the X is defective/broken/scratched ..."). Both capture the
# trailing reason so we can store it and read it back later.
#
# INSPECT — "find the defective part" / "which is defective" / etc. Must
# NOT match a sentence that is itself a teach statement, so we order the
# patterns deliberately in handle_command (teach first, then inspect).
TEACH_RE = re.compile(
    r"(?:"
    r"teach\s+defect(?:ive)?\b[\s,:]*(?P<reason1>.*)"
    # Natural form. Class capture greedily eats 1-3 words between
    # "this/that/the" and "is/has" so "the blue cube is defective" works
    # the same as "this cube is defective".
    r"|(?:this|that|the)\s+(?P<class2>[a-z]+(?:\s+[a-z]+){0,2}?)\s+(?:is|has)\s+(?:defective|broken|scratched|damaged|a\s+defect)\b[\s,:]*(?P<reason2>.*)"
    r")",
    re.IGNORECASE,
)
INSPECT_RE = re.compile(
    r"\b(find\s+(?:the\s+)?(?:defective|defect|bad\s+one)|which\s+(?:one\s+)?is\s+defective|inspect\s+(?:the\s+)?part|defective\s+part)\b",
    re.IGNORECASE,
)
# If the teach blurb begins with "<class> ..." (single short noun), we use
# that as the class. Otherwise everything is the reason and class = "object".
_CLASS_HINT_RE = re.compile(r"^\s*([a-z]+)\b\s*[:,-]?\s*(.*)$", re.IGNORECASE)


class ObjectDetection(BaseModel):
    """One colored object in the frame."""

    bbox: tuple[int, int, int, int]  # x, y, w, h
    center_px: tuple[float, float]
    area_px: float


def mean_hsv_in_bbox(
    frame: NDArray[np.uint8],
    bbox: tuple[int, int, int, int],
) -> tuple[float, float, float]:
    """Compute the mean HSV of the (already-saturated) pixels inside a bbox.

    Pixels below the saturation/value floor are excluded so the background
    paper doesn't dilute the object's true colour.
    """
    x, y, w, h = bbox
    region = frame[y : y + h, x : x + w]
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    s_mask = hsv[..., 1] >= HSV_SAT_MIN
    v_mask = hsv[..., 2] >= HSV_VAL_MIN
    mask = s_mask & v_mask
    # Fall back to whole-bbox mean if the mask is empty.
    mean = hsv.reshape(-1, 3).mean(axis=0) if not mask.any() else hsv[mask].mean(axis=0)
    return (float(mean[0]), float(mean[1]), float(mean[2]))


def detect_objects(
    frame: NDArray[np.uint8],
    workspace: Workspace | None = None,
) -> list[ObjectDetection]:
    """Locate colored objects in the frame via HSV saturation + contours.

    If ``workspace`` is given, drops any detection whose pixel centre projects
    outside the reachable rectangle so we don't pick up the Pi PCB / wires /
    background clutter sitting next to the cardboard.

    Returns sorted by area descending so callers can take the largest n.
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(
        hsv,
        (0, HSV_SAT_MIN, HSV_VAL_MIN),
        (180, 255, 255),
    )
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out: list[ObjectDetection] = []
    for c in contours:
        area = float(cv2.contourArea(c))
        if not (OBJECT_AREA_MIN_PX <= area <= OBJECT_AREA_MAX_PX):
            continue
        x, y, w, h = cv2.boundingRect(c)
        center_px = (float(x + w / 2), float(y + h / 2))
        if workspace is not None:
            world_xy = workspace.pixel_to_world(center_px)
            if not workspace.is_in_reachable_region(world_xy):
                continue
        out.append(
            ObjectDetection(
                bbox=(int(x), int(y), int(w), int(h)),
                center_px=center_px,
                area_px=area,
            )
        )
    out.sort(key=lambda d: d.area_px, reverse=True)
    return out


def _parse_teach(command: str) -> tuple[str, str | None]:
    """Pull (class, reason) out of a teach command.

    Supports both the explicit ("teach defect <reason>") and the natural
    ("this blue cube is defective because ...") teach phrasings. Examples::

        "teach defect"
            -> ("object", None)
        "teach defect cube"
            -> ("cube", None)
        "teach defect, this cube has scratched paint"
            -> ("cube", "this cube has scratched paint")
        "this blue cube is defective, paint is scratched"
            -> ("cube", "paint is scratched")
        "the green cube is broken"
            -> ("cube", None)
    """
    m = TEACH_RE.search(command)
    if m is None:
        return DEFAULT_OBJECT_CLASS, None

    # Natural form matched (group "class2"): class is captured directly,
    # reason is whatever follows the defect adjective.
    if m.group("class2"):
        cls = m.group("class2").strip().lower()
        reason = (m.group("reason2") or "").strip() or None
        # Drop common filler captured as class ("one", "thing", "it").
        if cls in {"one", "thing", "it"}:
            cls = DEFAULT_OBJECT_CLASS
        return cls, reason

    # Explicit "teach defect ..." form: walk the trailing blurb to optionally
    # split a leading noun off the reason.
    rest = (m.group("reason1") or "").strip()
    if not rest:
        return DEFAULT_OBJECT_CLASS, None
    hint = _CLASS_HINT_RE.match(rest)
    if hint:
        first = hint.group(1).lower()
        remainder = hint.group(2).strip() or None
        if first in {"this", "that", "the", "a", "an", "it", "here"}:
            return DEFAULT_OBJECT_CLASS, rest
        return first, remainder
    return DEFAULT_OBJECT_CLASS, rest


class DefectMode:
    """Teach/inspect lifecycle for the defect inspector."""

    name = "defect"

    def __init__(
        self,
        arm: Arm,
        kinematics: Kinematics,
        camera: Camera,
        router: ReasoningRouter,
        workspace: Workspace,
        basket_world_xy: tuple[float, float] = DEFAULT_BASKET_WORLD_XY,
    ) -> None:
        self._arm = arm
        self._ik = kinematics
        self._camera = camera
        self._router = router
        self._workspace = workspace
        self._basket = basket_world_xy
        self._active = False
        self._state = "IDLE"
        # The class most recently taught. Inspect prefers this if set;
        # otherwise it scans every class with at least one taught row.
        self._last_class: str | None = None

    async def start(self) -> None:
        self._active = True
        self._state = "READY"
        log.info("defect.start")

    async def stop(self) -> None:
        self._active = False
        self._state = "IDLE"
        log.info("defect.stop")

    async def handle_command(
        self, command: str, context: dict[str, Any]
    ) -> ModeResponse:
        del context
        if not self._active:
            return ModeResponse(
                spoken="Defect mode is not running.",
                action_taken="rejected",
                next_state={"reason": "inactive"},
            )
        # Teach patterns are checked before inspect because a sentence like
        # "the blue cube is defective" matches both — we want to treat it as
        # a teach (single object present) rather than an inspect.
        if TEACH_RE.search(command):
            cls, reason = _parse_teach(command)
            return await self._teach(cls, reason)
        if INSPECT_RE.search(command):
            return await self._inspect()
        return ModeResponse(
            spoken=(
                "Say 'teach defect <object>' to capture a defective part, "
                "or 'find defective part' to inspect."
            ),
            action_taken="help",
            next_state={"state": self._state},
        )

    async def _teach(self, object_class: str, reason: str | None = None) -> ModeResponse:
        self._state = "TEACHING"
        # Clear the arm out of the workspace before snapping so the gripper
        # doesn't occlude the cube under inspection. Swings the base to the
        # right and tucks the shoulder forward — both well outside the
        # workspace pixel rectangle.
        await self._clear_view_for_snapshot()
        try:
            frame = await self._camera.snapshot()
        except TimeoutError:
            self._state = "READY"
            return ModeResponse(
                spoken="I can't see the camera right now.",
                action_taken="camera_timeout",
                next_state={"state": self._state},
            )

        objects = detect_objects(frame, workspace=self._workspace)
        if len(objects) != 1:
            self._state = "READY"
            return ModeResponse(
                spoken=(
                    f"I see {len(objects)} {object_class}s. "
                    f"Place exactly one {object_class} to teach."
                ),
                action_taken="wrong_object_count",
                next_state={
                    "state": self._state,
                    "n_objects": len(objects),
                    "object_class": object_class,
                },
            )

        obj = objects[0]
        x, y, w, h = obj.bbox
        crop = frame[y : y + h, x : x + w]
        region = features.Region(x=x, y=y, w=w, h=h)
        _, descriptors = features.extract_orb_features(frame, region)
        color_hsv = mean_hsv_in_bbox(frame, obj.bbox)

        description_result = await self._router.describe_image(crop, DESCRIBE_PROMPT)
        description = description_result.text

        settings = get_settings()
        images_dir = settings.defects_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        # File stem uses a sanitised class so paths stay shell-safe.
        slug = re.sub(r"[^a-z0-9]+", "_", object_class.lower()).strip("_") or "object"
        image_path = images_dir / f"{slug}_{uuid.uuid4().hex[:8]}.jpg"
        cv2.imwrite(str(image_path), crop)

        blob = features.descriptors_to_blob(descriptors)
        record_id = defect_kb.add_defect(
            object_class,
            description,
            image_path,
            blob,
            color_hsv=color_hsv,
            reason=reason,
        )
        self._last_class = object_class

        self._state = "READY"
        log.info(
            "defect.taught",
            id=record_id,
            object_class=object_class,
            n_features=len(descriptors),
            color_hsv=color_hsv,
            reason=reason,
        )
        spoken_reason = f" You told me: {reason}." if reason else ""
        return ModeResponse(
            spoken=f"Defect captured for {object_class}.{spoken_reason}",
            action_taken=f"taught:{object_class}:{record_id}",
            visual=str(image_path),
            next_state={
                "state": self._state,
                "object_class": object_class,
                "record_id": record_id,
                "n_features": len(descriptors),
                "color_hsv": list(color_hsv),
                "description": description,
                "reason": reason,
            },
        )

    async def _clear_view_for_snapshot(self) -> None:
        """Swing the arm out of the workspace so the camera has a clean shot.

        Tucks the shoulder forward and rotates the base off-axis. Best-effort
        — if any joint command fails, we still try the snapshot.
        """
        try:
            await self._arm.jog_joint("shoulder", 55.0)
            await self._arm.jog_joint("base", 75.0)
        except Exception:
            log.exception("defect.clear_view_failed")

    def _collect_taught(self) -> list[defect_kb.DefectRecord]:
        """Pull every taught defect we might match against.

        Prefers the most recently taught class; falls back to "object" then
        to the legacy "cube" class so old data still inspects cleanly.
        """
        seen: set[int] = set()
        out: list[defect_kb.DefectRecord] = []
        classes: list[str] = []
        if self._last_class is not None:
            classes.append(self._last_class)
        for fallback in (DEFAULT_OBJECT_CLASS, "cube"):
            if fallback not in classes:
                classes.append(fallback)
        for cls in classes:
            for rec in defect_kb.get_defects_for_class(cls):
                if rec.id in seen:
                    continue
                seen.add(rec.id)
                out.append(rec)
        return out

    async def _inspect(self) -> ModeResponse:
        self._state = "INSPECTING"
        # Same auto-clear as teach so the camera always sees a clean bench
        # before scoring candidates. The pick happens immediately after this
        # detection, so the swing-aside motion is "free" — the arm has to
        # move anyway.
        await self._clear_view_for_snapshot()
        try:
            frame = await self._camera.snapshot()
        except TimeoutError:
            self._state = "READY"
            return ModeResponse(
                spoken="I can't see the camera right now.",
                action_taken="camera_timeout",
                next_state={"state": self._state},
            )

        objects = detect_objects(frame, workspace=self._workspace)
        if len(objects) < 2:
            self._state = "READY"
            return ModeResponse(
                spoken=f"I see {len(objects)} objects. Place at least two to compare.",
                action_taken="too_few_objects",
                next_state={"state": self._state, "n_objects": len(objects)},
            )

        taught = self._collect_taught()
        if not taught:
            self._state = "READY"
            return ModeResponse(
                spoken="No defects taught yet. Say 'teach defect' first.",
                action_taken="no_taught_defects",
                next_state={"state": self._state},
            )
        ref = taught[0]
        ref_class = ref.object_class

        # Score each candidate object. Primary signal is HSV colour distance
        # (works for solid-colour parts with no surface texture); ORB is a
        # tiebreaker when colours are close.
        scored: list[
            tuple[float, float, ObjectDetection, tuple[float, float, float]]
        ] = []
        ref_desc = (
            defect_kb._blob_to_descriptors(ref.feature_blob)
            if ref.feature_blob else None
        )
        for obj in objects:
            obj_hsv = mean_hsv_in_bbox(frame, obj.bbox)
            color_d = (
                defect_kb.color_distance(ref.color_hsv, obj_hsv)
                if ref.color_hsv is not None
                else 999.0
            )
            orb_score = 0.0
            if ref_desc is not None and len(ref_desc) > 0:
                region = features.Region(
                    x=obj.bbox[0], y=obj.bbox[1], w=obj.bbox[2], h=obj.bbox[3],
                )
                _, desc = features.extract_orb_features(frame, region)
                if len(desc) > 0:
                    orb_score = features.match_features(ref_desc, desc).score
            log.info(
                "defect.inspect.score",
                color_d=color_d,
                orb_score=orb_score,
                obj_hsv=obj_hsv,
                ref_class=ref_class,
            )
            scored.append((color_d, orb_score, obj, obj_hsv))

        # Lowest colour distance wins; break ties by higher ORB score.
        scored.sort(key=lambda t: (t[0], -t[1]))
        color_d, orb_score, obj, obj_hsv = scored[0]
        if ref.color_hsv is None or color_d > COLOR_MATCH_DISTANCE_MAX:
            self._state = "READY"
            return ModeResponse(
                spoken=f"None of the {ref_class}s match the taught defect colour.",
                action_taken="no_match",
                next_state={
                    "state": self._state,
                    "n_objects": len(objects),
                    "object_class": ref_class,
                    "best_color_distance": color_d,
                    "ref_hsv": list(ref.color_hsv) if ref.color_hsv else None,
                },
            )

        world_xy = self._workspace.pixel_to_world(obj.center_px)
        log.info(
            "defect.inspect.pick",
            world_xy=list(world_xy),
            color_d=color_d,
            orb_score=orb_score,
            object_class=ref_class,
        )
        await self._arm.pick_at(
            (float(world_xy[0]), float(world_xy[1])),
            self._ik,
            transit_z_mm=DEFECT_TRANSIT_Z_MM,
        )
        await self._arm.place_at(
            self._basket,
            self._ik,
            transit_z_mm=DEFECT_TRANSIT_Z_MM,
            place_z_mm=DEFECT_PLACE_Z_MM,
            gentle=True,
        )

        self._state = "READY"
        reason_blurb = (
            f" You taught me: {ref.reason}." if ref.reason else f" {ref.description}"
        )
        return ModeResponse(
            spoken=f"Picked the defective {ref_class}.{reason_blurb}",
            action_taken=f"picked:{ref.id}",
            visual=ref.image_path,
            next_state={
                "state": self._state,
                "object_class": ref_class,
                "color_distance": color_d,
                "orb_score": orb_score,
                "ref_id": ref.id,
                "ref_hsv": list(ref.color_hsv) if ref.color_hsv else None,
                "ref_reason": ref.reason,
                "obj_hsv": list(obj_hsv),
                "obj_world_xy": [float(world_xy[0]), float(world_xy[1])],
                "basket_world_xy": list(self._basket),
            },
        )


__all__ = [
    "DEFAULT_BASKET_WORLD_XY",
    "DEFAULT_OBJECT_CLASS",
    "OBJECT_AREA_MAX_PX",
    "OBJECT_AREA_MIN_PX",
    "DefectMode",
    "ObjectDetection",
    "detect_objects",
]
