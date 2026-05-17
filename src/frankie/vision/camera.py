"""MJPEG / RTSP camera wrapper.

Holds an OpenCV VideoCapture in a background reader thread. The reader
keeps only the latest frame, so latest_frame() / snapshot() never return
stale data. Auto-reconnects on read failure with exponential backoff.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
import time
from typing import TYPE_CHECKING

import cv2
import structlog

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray


log = structlog.get_logger(__name__)


RECONNECT_BACKOFF_S = (0.5, 1.0, 2.0, 4.0, 8.0)
SNAPSHOT_TIMEOUT_S = 5.0


class Camera:
    """Background frame grabber. Open once, read latest_frame on demand."""

    def __init__(self, url: str | int) -> None:
        self._url = url
        self._cap: cv2.VideoCapture | None = None
        self._latest: NDArray[np.uint8] | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._frame_event = threading.Event()
        self._opened = threading.Event()

    async def start(self) -> None:
        """Open the capture and spawn the reader thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._frame_event.clear()
        self._opened.clear()
        self._thread = threading.Thread(target=self._reader, name="camera-reader", daemon=True)
        self._thread.start()
        # Wait briefly for the first connection; if it fails, we let the
        # reader keep reconnecting in the background.
        await asyncio.get_event_loop().run_in_executor(None, self._opened.wait, 2.0)

    async def stop(self) -> None:
        """Stop the reader thread and release the capture."""
        self._stop.set()
        if self._thread:
            await asyncio.get_event_loop().run_in_executor(None, self._thread.join, 2.0)
        with self._lock:
            cap = self._cap
            self._cap = None
        if cap is not None:
            cap.release()

    async def latest_frame(self) -> NDArray[np.uint8] | None:
        """Return the freshest frame or None if not yet available."""
        with self._lock:
            return None if self._latest is None else self._latest.copy()

    async def snapshot(self) -> NDArray[np.uint8]:
        """Wait briefly for a guaranteed-fresh frame."""
        self._frame_event.clear()
        loop = asyncio.get_event_loop()
        got = await loop.run_in_executor(None, self._frame_event.wait, SNAPSHOT_TIMEOUT_S)
        if not got:
            raise TimeoutError(f"no frame from {self._url} in {SNAPSHOT_TIMEOUT_S}s")
        frame = await self.latest_frame()
        if frame is None:
            raise RuntimeError("frame_event set but latest is None")
        return frame

    # internals -----------------------------------------------------------

    def _open(self) -> cv2.VideoCapture:
        url = self._url
        backend = cv2.CAP_FFMPEG if isinstance(url, str) else cv2.CAP_ANY
        cap = cv2.VideoCapture(url, backend)
        with contextlib.suppress(Exception):
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _reader(self) -> None:
        attempt = 0
        while not self._stop.is_set():
            cap = self._open()
            with self._lock:
                self._cap = cap
            if not cap.isOpened():
                wait = RECONNECT_BACKOFF_S[min(attempt, len(RECONNECT_BACKOFF_S) - 1)]
                log.warning("camera.open_failed", url=self._url, wait_s=wait)
                attempt += 1
                if self._stop.wait(wait):
                    return
                continue
            log.info("camera.opened", url=self._url)
            self._opened.set()
            attempt = 0
            try:
                while not self._stop.is_set():
                    ok, frame = cap.read()
                    if not ok or frame is None:
                        log.warning("camera.read_failed", url=self._url)
                        break
                    with self._lock:
                        self._latest = frame  # type: ignore[assignment]
                    self._frame_event.set()
            finally:
                cap.release()
                with self._lock:
                    self._cap = None
            if self._stop.is_set():
                return
            wait = RECONNECT_BACKOFF_S[min(attempt, len(RECONNECT_BACKOFF_S) - 1)]
            log.info("camera.reconnect", url=self._url, wait_s=wait)
            attempt += 1
            time.sleep(wait)
