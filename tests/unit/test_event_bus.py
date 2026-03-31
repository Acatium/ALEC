"""Tests for the in-process event bus."""

from __future__ import annotations

from uuid import uuid4

import pytest

from alec.events.bus import EventBus
from alec.events.types import CycleStarted, EngagementStarted


@pytest.mark.asyncio
async def test_emit_and_subscribe():
    bus = EventBus()
    received = []

    async def handler(event: EngagementStarted) -> None:
        received.append(event)

    bus.subscribe(EngagementStarted, handler)
    eid = uuid4()
    await bus.emit(EngagementStarted(engagement_id=eid, name="test"))

    assert len(received) == 1
    assert received[0].engagement_id == eid
    assert received[0].name == "test"
    assert received[0].event_type == "engagement.started"


@pytest.mark.asyncio
async def test_multiple_handlers():
    bus = EventBus()
    results = []

    async def h1(event: CycleStarted) -> None:
        results.append("h1")

    async def h2(event: CycleStarted) -> None:
        results.append("h2")

    bus.subscribe(CycleStarted, h1)
    bus.subscribe(CycleStarted, h2)

    await bus.emit(CycleStarted(engagement_id=uuid4(), cycle_number=1))
    assert set(results) == {"h1", "h2"}


@pytest.mark.asyncio
async def test_error_isolation():
    bus = EventBus()
    results = []

    async def bad_handler(event: CycleStarted) -> None:
        raise ValueError("boom")

    async def good_handler(event: CycleStarted) -> None:
        results.append("ok")

    bus.subscribe(CycleStarted, bad_handler)
    bus.subscribe(CycleStarted, good_handler)

    await bus.emit(CycleStarted(engagement_id=uuid4(), cycle_number=1))
    assert results == ["ok"]


@pytest.mark.asyncio
async def test_type_isolation():
    bus = EventBus()
    received = []

    async def handler(event: EngagementStarted) -> None:
        received.append(event)

    bus.subscribe(EngagementStarted, handler)

    # Emit a different event type — handler should NOT fire
    await bus.emit(CycleStarted(engagement_id=uuid4(), cycle_number=1))
    assert len(received) == 0


@pytest.mark.asyncio
async def test_no_handlers():
    bus = EventBus()
    # Should not raise
    await bus.emit(CycleStarted(engagement_id=uuid4(), cycle_number=1))


def test_handler_count():
    bus = EventBus()

    async def h(e: CycleStarted) -> None:
        pass

    assert bus.handler_count(CycleStarted) == 0
    bus.subscribe(CycleStarted, h)
    assert bus.handler_count(CycleStarted) == 1


def test_event_frozen():
    e = EngagementStarted(engagement_id=uuid4(), name="test")
    with pytest.raises(AttributeError):
        e.name = "changed"  # type: ignore[misc]
