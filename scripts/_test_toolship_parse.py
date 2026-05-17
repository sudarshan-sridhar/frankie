"""Smoke test for toolship intent parsing + tools.json loading."""

from __future__ import annotations

from frankie.modes.toolship import load_tools, parse_tool_name


def main() -> int:
    assert parse_tool_name("M6") == "M6"
    assert parse_tool_name("give me M3") == "M3"
    assert parse_tool_name("M4 bolt please") == "M4"
    assert parse_tool_name("m5 phillips") == "M5"
    assert parse_tool_name("M 6") == "M6"  # tolerates space
    assert parse_tool_name("hand me the small one") is None
    assert parse_tool_name("") is None

    cfg = load_tools()
    assert set(cfg.tools.keys()) == {"M3", "M4", "M5", "M6"}
    assert cfg.tools["M6"].warning.startswith("Don't over-tighten")
    print("toolship parse + load: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
