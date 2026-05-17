"""Camera background reader: smoke test against a stubbed VideoCapture."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import numpy as np

from frankie.vision import camera as cam_mod


class _FakeCap:
    """Drop-in stand-in for cv2.VideoCapture that always returns one frame."""

    def __init__(self, *_: object, **__: object) -> None:
        self._open = True

    def isOpened(self) -> bool:
        return self._open

    def read(self) -> tuple[bool, np.ndarray]:
        return True, np.zeros((720, 1280, 3), dtype=np.uint8)

    def set(self, *_: object, **__: object) -> bool:
        return True

    def release(self) -> None:
        self._open = False


async def test_camera_start_yields_a_frame() -> None:
    with patch.object(cam_mod.cv2, "VideoCapture", _FakeCap):
        cam = cam_mod.Camera("fake://")
        try:
            await cam.start()
            # give the reader thread a moment to push a frame
            await asyncio.sleep(0.1)
            frame = await cam.latest_frame()
            assert frame is not None
            assert frame.shape == (720, 1280, 3)
        finally:
            await cam.stop()
