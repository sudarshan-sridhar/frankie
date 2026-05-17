"""Centralized prompt strings for Claude Vision and reasoning calls.

Keeping prompts here (not inline in business logic) means we can iterate on
wording without touching call sites and we can A/B test against fixtures.
"""

from __future__ import annotations

DEFECT_DESCRIBE = (
    "You are inspecting a small machined part. Describe the defect visible "
    "in this image in one sentence. Be specific about location and type."
)

DEFECT_COMPARE = (
    "Two images of the same part class. Decide whether the second image "
    "shows the same defect as the first. Reply 'yes' or 'no' on the first "
    "line, then a one-sentence reason."
)

CHESS_BOARD_STATE = (
    "This image shows a chess board from above. Return JSON mapping each "
    "occupied square (algebraic, e.g. 'e4') to a piece code "
    "(uppercase=white, lowercase=black, e.g. 'P', 'n'). Return only JSON."
)
