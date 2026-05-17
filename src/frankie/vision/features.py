"""ORB feature extraction and matching for the defect inspector.

OpenCV ORB with nfeatures=500 and a BFMatcher with crossCheck=True. Region
selection is optional: callers can pass a bounding box to limit features
to a detected cube. Match scoring is the count of mutual nearest matches
normalised by the candidate feature count.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeAlias

import cv2
import numpy as np
from pydantic import BaseModel

if TYPE_CHECKING:
    from numpy.typing import NDArray

Keypoints: TypeAlias = list[cv2.KeyPoint]
Descriptors: TypeAlias = "NDArray[np.uint8]"


# Tuned for ~3 cm cubes filling 80-120 px in the frame. 500 features is enough
# to capture surface texture differences (scratches, dings) without bloating
# the descriptor blob in SQLite.
ORB_NFEATURES = 500

# A match is "good" if the cross-checked Hamming distance is below this. ORB
# descriptors are 256 bits, so 64 is a quarter-distance which catches scratched
# surfaces while rejecting random clutter.
GOOD_MATCH_HAMMING_THRESHOLD = 64

# Below this normalised score we say the two descriptor sets don't share a
# defect. Tuned against synthetic same/different cube pairs.
IS_MATCH_THRESHOLD = 0.25


class Region(BaseModel):
    """Axis-aligned bounding box in pixels."""

    x: int
    y: int
    w: int
    h: int


class MatchResult(BaseModel):
    """Result of comparing two descriptor sets."""

    n_matches: int
    score: float
    is_match: bool


def _orb() -> cv2.ORB:
    return cv2.ORB_create(nfeatures=ORB_NFEATURES)


def extract_orb_features(
    image: NDArray[np.uint8],
    region: Region | None = None,
) -> tuple[Keypoints, Descriptors]:
    """Extract ORB keypoints and descriptors, optionally restricted to region.

    Region is applied as a mask so keypoint coordinates stay in the original
    image frame (useful when the caller wants to draw matches on the full
    snapshot later).
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    mask = None
    if region is not None:
        mask = np.zeros(gray.shape, dtype=np.uint8)
        mask[region.y : region.y + region.h, region.x : region.x + region.w] = 255
    keypoints, descriptors = _orb().detectAndCompute(gray, mask)
    if descriptors is None:
        # OpenCV returns None when no features found; normalise to empty array.
        descriptors = np.zeros((0, 32), dtype=np.uint8)
    return list(keypoints), descriptors


def match_features(ref_desc: Descriptors, test_desc: Descriptors) -> MatchResult:
    """Cross-check BF match. Score = good_matches / max(ref_count, test_count).

    Score in [0, 1]. 0 = no overlap, 1 = every reference feature matched.
    is_match flips at IS_MATCH_THRESHOLD.
    """
    if ref_desc.size == 0 or test_desc.size == 0:
        return MatchResult(n_matches=0, score=0.0, is_match=False)
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = matcher.match(ref_desc, test_desc)
    good = [m for m in matches if m.distance < GOOD_MATCH_HAMMING_THRESHOLD]
    denom = max(len(ref_desc), len(test_desc))
    score = len(good) / denom if denom > 0 else 0.0
    return MatchResult(
        n_matches=len(good),
        score=score,
        is_match=score >= IS_MATCH_THRESHOLD,
    )


def descriptors_to_blob(descriptors: Descriptors) -> bytes:
    """Serialise descriptors for SQLite. Inverse of defect_kb._blob_to_descriptors."""
    return descriptors.astype(np.uint8).tobytes()
