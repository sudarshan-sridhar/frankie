"""Placeholder; real KB tests land in Phase 4."""

from __future__ import annotations

from frankie.reasoning.defect_kb import _connect


def test_schema_creates_on_first_connect() -> None:
    with _connect() as conn:
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        names = {row[0] for row in cur.fetchall()}
        assert "defects" in names
