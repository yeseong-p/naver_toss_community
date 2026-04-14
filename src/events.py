"""In-process pub/sub for SSE fan-out."""
import asyncio
from typing import Any

from src import config


class EventBus:
    def __init__(self):
        self._subscribers: set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=config.SSE_QUEUE_MAXSIZE)
        async with self._lock:
            self._subscribers.add(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue):
        async with self._lock:
            self._subscribers.discard(q)

    async def publish(self, event: dict[str, Any]):
        dead = []
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            await self.unsubscribe(q)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


bus = EventBus()

# Shared health state so dashboard can show poller status.
health: dict[str, dict] = {
    "naver": {"last_ok": None, "last_error": None, "consecutive_errors": 0},
    "toss": {"last_ok": None, "last_error": None, "consecutive_errors": 0},
}
