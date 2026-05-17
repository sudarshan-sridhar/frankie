"""SQLite-backed defect knowledge base.

Persists taught defects (image, free-text description, ORB descriptor blob)
keyed by an object class. The Phase 4 defect mode reads from here when
deciding which cube to pick.
"""

from __future__ import annotations

import contextlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from pydantic import BaseModel

from frankie.config import get_settings

if TYPE_CHECKING:
    from numpy.typing import NDArray


SCHEMA = """
CREATE TABLE IF NOT EXISTS defects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_class TEXT NOT NULL,
    description TEXT NOT NULL,
    image_path TEXT NOT NULL,
    feature_blob BLOB,
    color_h REAL,
    color_s REAL,
    color_v REAL,
    reason TEXT,
    created_at TEXT NOT NULL
);
"""

# Idempotent migration for existing DBs. Each ALTER fails silently if the
# column already exists.
MIGRATIONS = (
    "ALTER TABLE defects ADD COLUMN color_h REAL",
    "ALTER TABLE defects ADD COLUMN color_s REAL",
    "ALTER TABLE defects ADD COLUMN color_v REAL",
    "ALTER TABLE defects ADD COLUMN reason TEXT",
)

# A 32-byte ORB descriptor row is one feature; the blob is rows*32 bytes.
# Match threshold is the minimum mean-Hamming inverse score below which a
# candidate is rejected. Tuned empirically; revisit if recall is poor.
ORB_DESC_BYTES_PER_ROW = 32
MATCH_SCORE_THRESHOLD = 0.30


class DefectRecord(BaseModel):
    """One row in the defects table."""

    id: int
    object_class: str
    description: str
    image_path: str
    feature_blob: bytes | None
    color_hsv: tuple[float, float, float] | None = None
    reason: str | None = None
    created_at: str


def _db_path() -> Path:
    return get_settings().defects_dir / "defects.sqlite"


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(SCHEMA)
    # Apply column migrations; each ALTER fails if column exists, which is fine.
    for stmt in MIGRATIONS:
        with contextlib.suppress(sqlite3.OperationalError):
            conn.execute(stmt)
    return conn


def _row_to_record(
    row: tuple[int, str, str, str, bytes | None, float | None, float | None, float | None, str | None, str],
) -> DefectRecord:
    color_hsv: tuple[float, float, float] | None = None
    if row[5] is not None and row[6] is not None and row[7] is not None:
        color_hsv = (float(row[5]), float(row[6]), float(row[7]))
    return DefectRecord(
        id=row[0],
        object_class=row[1],
        description=row[2],
        image_path=row[3],
        feature_blob=row[4],
        color_hsv=color_hsv,
        reason=row[8],
        created_at=row[9],
    )


def add_defect(
    object_class: str,
    description: str,
    image_path: Path,
    feature_blob: bytes,
    color_hsv: tuple[float, float, float] | None = None,
    reason: str | None = None,
) -> int:
    """Insert a new defect row and return its id."""
    now = datetime.now(UTC).isoformat()
    h, s, v = (color_hsv if color_hsv is not None else (None, None, None))
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO defects "
            "(object_class, description, image_path, feature_blob, color_h, color_s, color_v, reason, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (object_class, description, str(image_path), feature_blob, h, s, v, reason, now),
        )
        conn.commit()
        return int(cursor.lastrowid or 0)


def get_defects_for_class(object_class: str) -> list[DefectRecord]:
    """Return all taught defects for the given class, newest first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, object_class, description, image_path, feature_blob, "
            "color_h, color_s, color_v, reason, created_at "
            "FROM defects WHERE object_class = ? ORDER BY id DESC",
            (object_class,),
        ).fetchall()
    return [_row_to_record(r) for r in rows]


def hue_distance(h1: float, h2: float) -> float:
    """Distance between two hues on the [0, 180] circle used by OpenCV HSV."""
    d = abs(h1 - h2)
    return min(d, 180.0 - d)


def color_distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    """Weighted HSV distance. Hue dominates because hue is the identity signal."""
    return hue_distance(a[0], b[0]) + 0.25 * abs(a[1] - b[1]) + 0.10 * abs(a[2] - b[2])


def _blob_to_descriptors(blob: bytes) -> NDArray[np.uint8]:
    """Reverse the serialisation used by features.match_features."""
    arr = np.frombuffer(blob, dtype=np.uint8)
    rows = arr.size // ORB_DESC_BYTES_PER_ROW
    return arr[: rows * ORB_DESC_BYTES_PER_ROW].reshape(rows, ORB_DESC_BYTES_PER_ROW)


def find_best_match(
    object_class: str, test_descriptors: NDArray[np.uint8]
) -> DefectRecord | None:
    """Return the best-matching taught defect, or None below threshold.

    Uses the project-wide BFMatcher (NORM_HAMMING + crossCheck) wrapped by
    `vision.features.match_features`. Imported lazily so this module stays
    importable in environments without OpenCV (e.g. test fixtures).
    """
    from frankie.vision.features import match_features

    candidates = get_defects_for_class(object_class)
    best: tuple[float, DefectRecord] | None = None
    for record in candidates:
        if not record.feature_blob:
            continue
        ref = _blob_to_descriptors(record.feature_blob)
        result = match_features(ref, test_descriptors)
        if best is None or result.score > best[0]:
            best = (result.score, record)
    if best is None or best[0] < MATCH_SCORE_THRESHOLD:
        return None
    return best[1]


__all__ = [
    "MATCH_SCORE_THRESHOLD",
    "DefectRecord",
    "_connect",
    "_db_path",
    "add_defect",
    "color_distance",
    "find_best_match",
    "get_defects_for_class",
    "hue_distance",
]
