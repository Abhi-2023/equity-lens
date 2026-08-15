"""In-memory pub/sub used to power the SSE live-trace stream (Section 2.2 / 4 step 2).

One asyncio.Queue per job_id, plus a small replay buffer per job — the report
job starts as a background task the instant POST /reports returns, so the
frontend's SSE connection almost always arrives a beat after the first
events fire. Without a buffer those events would just be lost. Swap for
Redis pub/sub (with a capped stream) if the API ever runs as more than one
process — the interface (`publish` / `subscribe`) stays the same.
"""
from __future__ import annotations

import asyncio
import datetime
from collections import defaultdict, deque
from typing import Any, AsyncIterator

_SENTINEL = object()
_REPLAY_BUFFER_SIZE = 200


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._history: dict[str, deque[dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=_REPLAY_BUFFER_SIZE)
        )
        self._closed: set[str] = set()

    def subscribe(self, job_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        for event in self._history.get(job_id, ()):
            queue.put_nowait(event)
        if job_id in self._closed:
            queue.put_nowait(_SENTINEL)
        else:
            self._subscribers[job_id].append(queue)
        return queue

    def unsubscribe(self, job_id: str, queue: asyncio.Queue) -> None:
        subs = self._subscribers.get(job_id, [])
        if queue in subs:
            subs.remove(queue)
        if not subs:
            self._subscribers.pop(job_id, None)

    async def publish(self, job_id: str, event: dict[str, Any]) -> None:
        event.setdefault("ts", datetime.datetime.now(datetime.timezone.utc).isoformat())
        self._history[job_id].append(event)
        for queue in list(self._subscribers.get(job_id, [])):
            await queue.put(event)

    async def close(self, job_id: str) -> None:
        self._closed.add(job_id)
        for queue in list(self._subscribers.get(job_id, [])):
            await queue.put(_SENTINEL)


bus = EventBus()


async def stream_job_events(job_id: str) -> AsyncIterator[dict[str, Any]]:
    queue = bus.subscribe(job_id)
    try:
        while True:
            event = await queue.get()
            if event is _SENTINEL:
                break
            yield event
    finally:
        bus.unsubscribe(job_id, queue)
