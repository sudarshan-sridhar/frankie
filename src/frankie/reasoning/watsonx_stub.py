"""watsonx.ai Granite stub.

At HackMI 2026 the tool-handover safety warning will route through IBM
watsonx Granite. Until then this module returns hardcoded strings so the
demo runs end-to-end. Replace get_tool_warning at hackathon time.
"""

from __future__ import annotations

_HARDCODED_WARNINGS: dict[str, str] = {
    "M3": "Small bolts. Easy to strip. Light touch.",
    "M4": "Standard fastener. Check threads.",
    "M5": "Medium torque. Watch for cross-threading.",
    "M6": "Don't over-tighten on aluminum. Max 8 Nm.",
}


def get_tool_warning(tool_name: str) -> str:
    """Return a safety warning for the named tool."""
    return _HARDCODED_WARNINGS.get(tool_name, "No specific guidance. Use standard care.")
