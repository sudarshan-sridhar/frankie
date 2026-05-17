"""Smoke test for vision.features + reasoning.defect_kb.

Generates a synthetic image, extracts ORB features, round-trips through
SQLite + descriptor blob serialisation, and verifies self-match scores
high while random-vs-random scores low.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import cv2
import numpy as np

from frankie.reasoning import defect_kb
from frankie.vision import features


def main() -> int:
    rng = np.random.default_rng(seed=42)
    # Use a textured image (random noise then blur) so ORB finds features.
    img1 = rng.integers(0, 255, (300, 300, 3), dtype=np.uint8)
    img1 = cv2.GaussianBlur(img1, (3, 3), 0)
    img2 = rng.integers(0, 255, (300, 300, 3), dtype=np.uint8)
    img2 = cv2.GaussianBlur(img2, (3, 3), 0)

    kp1, d1 = features.extract_orb_features(img1)
    kp2, d2 = features.extract_orb_features(img2)
    print(f"img1 features: {len(d1)}  img2: {len(d2)}")

    r_self = features.match_features(d1, d1)
    r_diff = features.match_features(d1, d2)
    print(f"self-match: n={r_self.n_matches} score={r_self.score:.3f} is_match={r_self.is_match}")
    print(f"diff-match: n={r_diff.n_matches} score={r_diff.score:.3f} is_match={r_diff.is_match}")
    assert r_self.is_match, "self-match should be true"
    assert not r_diff.is_match, "random vs random should NOT match"

    # Round-trip through SQLite.
    with tempfile.TemporaryDirectory() as tmp:
        img_path = Path(tmp) / "ref.jpg"
        cv2.imwrite(str(img_path), img1)
        blob = features.descriptors_to_blob(d1)
        # Force the KB to use a temp directory so we don't pollute the live db.
        original_db = defect_kb._db_path
        defect_kb._db_path = lambda: Path(tmp) / "test.sqlite"  # type: ignore[assignment]
        try:
            row_id = defect_kb.add_defect("cube", "ref defect", img_path, blob)
            print(f"inserted id={row_id}")
            rows = defect_kb.get_defects_for_class("cube")
            assert len(rows) == 1
            print(f"retrieved {len(rows)} row, blob {len(rows[0].feature_blob or b'')} bytes")
            best = defect_kb.find_best_match("cube", d1)
            assert best is not None and best.id == row_id
            print(f"find_best_match on self: id={best.id}")
            best_other = defect_kb.find_best_match("cube", d2)
            print(f"find_best_match on different image: {best_other}")
        finally:
            defect_kb._db_path = original_db  # type: ignore[assignment]
    print("smoke test PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
