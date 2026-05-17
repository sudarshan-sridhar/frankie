"""Tiny fan-out event broker used by /ws/state to surface side events.

Producers call ``publish``; subscribers get an asyncio.Queue from
``subscribe`` and drain it. Queues are bounded; if a slow consumer
fills its queue we drop the oldest event instead of blocking the
producer. Used by the calibration watcher to surface
``workspace.stale`` / ``workspace.recalibrated`` notifications.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

import structlog

log = structlog.get_logger(__name__)


class EventBroker:
    """In-process pub/sub for lightweight notifications."""

    def __init__(self, max_queue: int = 32) -> None:
        self._subscribers: list[asyncio.Queue[dict[str, Any]]] = []
        self._lock = asyncio.Lock()
        self._max_queue = max_queue

    async def publish(self, event: dict[str, Any]) -> None:
        """Send ``event`` to every active subscriber."""
        async with self._lock:
            targets = list(self._subscribers)
        for queue in targets:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(event)

    async def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        """Register a new subscriber and return its queue."""
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._max_queue)
        async with self._lock:
            self._subscribers.append(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        """Drop a subscriber queue."""
        async with self._lock:
            with contextlib.suppress(ValueError):
                self._subscribers.remove(queue)
