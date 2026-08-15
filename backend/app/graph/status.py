"""Per-node status emission — feeds both the SSE trace panel and (indirectly)
LangSmith, per Section 6: "Each node emits a status event on entry/exit —
this event stream is what feeds both the SSE trace panel and the LangSmith run."
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

from app.events import bus


class NodeStatusReporter:
    def __init__(self, job_id: str, node: str) -> None:
        self.job_id = job_id
        self.node = node
        self._start = 0.0

    async def message(self, text: str) -> None:
        await bus.publish(
            self.job_id,
            {
                "node": self.node,
                "status": "running",
                "message": text,
                "elapsed_ms": int((time.monotonic() - self._start) * 1000),
            },
        )


@asynccontextmanager
async def node_status(job_id: str, node: str, start_message: str) -> AsyncIterator[NodeStatusReporter]:
    reporter = NodeStatusReporter(job_id, node)
    reporter._start = time.monotonic()
    await bus.publish(job_id, {"node": node, "status": "started", "message": start_message, "elapsed_ms": 0})
    try:
        yield reporter
    except Exception as exc:
        await bus.publish(
            job_id,
            {
                "node": node,
                "status": "error",
                "message": str(exc),
                "elapsed_ms": int((time.monotonic() - reporter._start) * 1000),
            },
        )
        raise
    else:
        await bus.publish(
            job_id,
            {
                "node": node,
                "status": "completed",
                "message": f"{node} finished",
                "elapsed_ms": int((time.monotonic() - reporter._start) * 1000),
            },
        )
