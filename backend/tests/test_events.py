import pytest

from app.events import EventBus


@pytest.mark.asyncio
async def test_subscriber_receives_published_event():
    bus = EventBus()
    queue = bus.subscribe("job-1")
    await bus.publish("job-1", {"node": "planner", "status": "started"})
    event = await queue.get()
    assert event["node"] == "planner"
    assert "ts" in event


@pytest.mark.asyncio
async def test_late_subscriber_replays_history():
    bus = EventBus()
    await bus.publish("job-2", {"node": "planner", "status": "started"})
    await bus.publish("job-2", {"node": "planner", "status": "completed"})

    # subscriber arrives *after* both events were published
    queue = bus.subscribe("job-2")
    first = await queue.get()
    second = await queue.get()
    assert first["status"] == "started"
    assert second["status"] == "completed"


@pytest.mark.asyncio
async def test_close_after_subscribe_sends_sentinel_eventually():
    bus = EventBus()
    queue = bus.subscribe("job-3")
    await bus.close("job-3")
    # subsequent subscriber to a closed job should immediately get closed out
    late_queue = bus.subscribe("job-3")
    from app.events import _SENTINEL

    assert await late_queue.get() is _SENTINEL
