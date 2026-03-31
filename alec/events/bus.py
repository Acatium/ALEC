"""In-process async event bus with type-safe subscriptions."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Callable, Coroutine

import structlog

from alec.events.types import Event

logger = structlog.get_logger()

# Type alias for async event handlers
EventHandler = Callable[[Any], Coroutine[Any, Any, None]]


class EventBus:
    """In-process async pub/sub event bus.

    Type-safe: subscribe to specific event classes.
    Error isolation: one handler failure doesn't break others.
    """

    def __init__(self) -> None:
        self._handlers: dict[type[Event], list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: type[Event], handler: EventHandler) -> None:
        """Subscribe a handler to a specific event type."""
        self._handlers[event_type].append(handler)

    async def emit(self, event: Event) -> None:
        """Emit an event to all subscribed handlers.

        Handlers run concurrently. Errors in one handler don't affect others.
        """
        event_class = type(event)
        handlers = self._handlers.get(event_class, [])
        if not handlers:
            return

        results = await asyncio.gather(
            *(h(event) for h in handlers),
            return_exceptions=True,
        )

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    "event.handler.error",
                    event_type=event.event_type,
                    handler=handlers[i].__qualname__,
                    error=str(result),
                )

    def handler_count(self, event_type: type[Event]) -> int:
        """Return number of handlers for an event type."""
        return len(self._handlers.get(event_type, []))
