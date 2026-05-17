"""Reasoning router: Granite primary, Claude fallback.

Tries IBM Granite via watsonx.ai first. If the call fails (network,
auth, empty body) it transparently falls back to Anthropic Claude.
Callers don't know which model answered; the model used is logged
server-side for telemetry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np
import structlog

from frankie.reasoning.granite import GraniteClient, GraniteError

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from frankie.vision.claude_vision import ClaudeVision

log = structlog.get_logger(__name__)

# A response shorter than this many characters is treated as "Granite gave up";
# we fall back to Claude. Tuned for shop-floor commands where even minimal
# replies should clear this bar.
_MIN_USEFUL_REPLY_CHARS = 6


@dataclass
class ReasoningResult:
    """Result of a routed reasoning call. Includes which model answered."""

    text: str
    model_used: str  # "granite" or "claude"


class ReasoningRouter:
    """Granite-first, Claude-second router for chat + vision calls."""

    def __init__(
        self,
        granite: GraniteClient | None,
        claude: ClaudeVision | None,
    ) -> None:
        if granite is None and claude is None:
            raise ValueError(
                "ReasoningRouter requires at least one of granite, claude"
            )
        self._granite = granite
        self._claude = claude

    @property
    def has_granite(self) -> bool:
        return self._granite is not None

    @property
    def has_claude(self) -> bool:
        return self._claude is not None

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int = 512,
        temperature: float = 0.7,
    ) -> ReasoningResult:
        """Route a chat call. Granite first, Claude fallback."""
        if self._granite is not None:
            try:
                text = await self._granite.chat(
                    messages, max_tokens=max_tokens, temperature=temperature,
                )
            except GraniteError as exc:
                log.warning("reasoning.granite_failed", err=str(exc))
            else:
                if len(text.strip()) >= _MIN_USEFUL_REPLY_CHARS:
                    log.info("reasoning.granite_ok", chars=len(text))
                    return ReasoningResult(text=text, model_used="granite")
                log.warning("reasoning.granite_empty", chars=len(text))

        # Fallback to Claude.
        if self._claude is None:
            raise RuntimeError("Granite failed and Claude fallback not configured")

        prompt = _messages_to_prompt(messages)
        text = await self._claude.describe(_BLANK_FRAME, prompt)
        return ReasoningResult(text=text, model_used="claude")

    async def describe_image(
        self,
        image_bgr: NDArray,
        prompt: str,
    ) -> ReasoningResult:
        """Route a vision call. Claude first (accurate), Granite Vision fallback.

        Reversed from chat() on purpose: the small Granite-Vision-3-2-2b model
        hallucinates objects that aren't on the bench (a known failure mode
        for sub-3B vision models on shop-floor photos), which is unacceptable
        for the defect / inspection demo. Claude vision sees what is actually
        there. Granite Vision stays as a fallback only if Claude is unwired.
        """
        if self._claude is not None:
            try:
                text = await self._claude.describe(image_bgr, prompt)
            except Exception as exc:  # noqa: BLE001 — broad-ok; we want any failure to fall through
                log.warning("reasoning.claude_vision_failed", err=str(exc))
            else:
                if len(text.strip()) >= _MIN_USEFUL_REPLY_CHARS:
                    log.info("reasoning.claude_vision_ok", chars=len(text))
                    return ReasoningResult(text=text, model_used="claude")
                log.warning("reasoning.claude_vision_empty", chars=len(text))

        if self._granite is None:
            raise RuntimeError("Claude Vision failed and Granite fallback not configured")

        text = await self._granite.describe_image(image_bgr, prompt)
        return ReasoningResult(text=text, model_used="granite")

    async def aclose(self) -> None:
        if self._granite is not None:
            await self._granite.aclose()


def _messages_to_prompt(messages: list[dict[str, Any]]) -> str:
    """Flatten a chat-format messages list into one prompt for vision-only fallback."""
    parts: list[str] = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if isinstance(content, list):
            text_parts = [
                p.get("text", "") for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            ]
            content = " ".join(text_parts)
        parts.append(f"{role.upper()}: {content}")
    return "\n".join(parts)


# Tiny blank frame for the rare case where Claude vision is the fallback for
# a text-only chat: Claude's describe() requires an image input. The frame
# content is ignored; only the prompt matters.
_BLANK_FRAME = np.zeros((4, 4, 3), dtype=np.uint8)
