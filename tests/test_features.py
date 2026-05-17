"""Placeholder; real ORB tests land in Phase 4."""

from __future__ import annotations

from frankie.vision.features import MatchResult, Region


def test_match_result_construct() -> None:
    r = MatchResult(n_matches=42, score=0.73, is_match=True)
    assert r.is_match
    box = Region(x=10, y=10, w=50, h=50)
    assert box.w == 50
