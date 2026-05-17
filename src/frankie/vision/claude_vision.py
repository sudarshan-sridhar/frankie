"""Claude Vision client.

Async wrapper around the Anthropic SDK that takes numpy frames, encodes
them as base64 JPEGs (quality 85), and sends them with a free-form text
prompt. Logs each call to data/logs/ via structlog.

Model defaults to claude-sonnet-4-5; override at construction.
"""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING

import cv2
import structlog
from anthropic import AsyncAnthropic

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

log = structlog.get_logger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
JPEG_QUALITY = 85
MAX_TOKENS = 512


def _encode_jpeg(frame: NDArray[np.uint8]) -> str:
    """Encode a BGR frame as base64 JPEG at the configured quality."""
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
    if not ok:
        raise RuntimeError("cv2.imencode failed for JPEG")
    return base64.b64encode(buf.tobytes()).decode("ascii")


class ClaudeVision:
    """Async client for vision-flavored Claude calls."""

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL) -> None:
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is empty")
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    async def describe(self, image: NDArray[np.uint8], prompt: str) -> str:
        """Return Claude's free-form description of image given prompt."""
        return await self._call(prompt, [image])

    async def compare(
        self,
        ref_image: NDArray[np.uint8],
        test_image: NDArray[np.uint8],
        prompt: str,
    ) -> str:
        """Compare two images under prompt."""
        return await self._call(prompt, [ref_image, test_image])

    async def classify(self, image: NDArray[np.uint8], categories: list[str]) -> str:
        """Return the best matching category for image."""
        category_list = ", ".join(repr(c) for c in categories)
        prompt = (
            f"Classify this image into one of the following categories: {category_list}.\n"
            "Reply with ONLY the chosen category string, no other words."
        )
        return await self._call(prompt, [image])

    async def _call(self, prompt: str, frames: list[NDArray[np.uint8]]) -> str:
        content: list[dict[str, object]] = []
        for f in frames:
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": _encode_jpeg(f),
                    },
                }
            )
        content.append({"type": "text", "text": prompt})

        log.info("vision.call", n_images=len(frames), model=self._model)
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": content}],  # type: ignore[typeddict-item]
        )
        text_parts: list[str] = []
        for block in response.content:
            if getattr(block, "type", "") == "text":
                text_parts.append(getattr(block, "text", ""))
        text = "".join(text_parts).strip()
        log.info("vision.response", chars=len(text))
        return text
