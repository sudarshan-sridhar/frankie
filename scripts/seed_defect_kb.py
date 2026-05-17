"""Initialize the defect SQLite schema (Phase 4 implementation).

Creates data/defects/defects.sqlite with the defects table if missing.
Used once during setup and as a smoke check after deploys.
"""

from __future__ import annotations

import sys

from frankie.reasoning.defect_kb import _connect


def main() -> int:
    """Open the DB once to trigger schema creation."""
    with _connect() as conn:
        conn.execute("SELECT COUNT(*) FROM defects")
    print("defect KB initialized.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
