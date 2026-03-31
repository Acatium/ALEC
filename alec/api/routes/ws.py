"""WebSocket route for real-time event streaming."""

from __future__ import annotations

import json
from collections import defaultdict

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from alec.events.bus import EventBus
from alec.events.types import Event

logger = structlog.get_logger()
router = APIRouter()

# Active WebSocket connections per engagement
_connections: dict[str, set[WebSocket]] = defaultdict(set)


def _make_handler(engagement_id: str) -> object:
    """Create an event handler that broadcasts to WebSocket clients."""

    async def handler(event: Event) -> None:
        data = event.to_dict()
        # Filter: only forward events for this engagement
        event_eid = data.get("engagement_id")
        if event_eid and event_eid != engagement_id:
            return

        payload = json.dumps(data)
        dead: list[WebSocket] = []
        for ws in _connections[engagement_id]:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)

        for ws in dead:
            _connections[engagement_id].discard(ws)

    return handler


@router.websocket("/ws/{engagement_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    engagement_id: str,
) -> None:
    await websocket.accept()
    _connections[engagement_id].add(websocket)

    event_bus: EventBus = websocket.app.state.event_bus
    handler = _make_handler(engagement_id)

    # Subscribe to all event types
    from alec.events.types import (
        BudgetWarning,
        ConsolidationCompleted,
        ConsolidationStarted,
        ConvergenceReached,
        CycleCompleted,
        CycleStarted,
        EngagementStarted,
        WorkerCompleted,
        WorkerDispatched,
        WorkerProgress,
    )

    event_types = [
        EngagementStarted,
        CycleStarted,
        CycleCompleted,
        WorkerDispatched,
        WorkerProgress,
        WorkerCompleted,
        ConvergenceReached,
        BudgetWarning,
        ConsolidationStarted,
        ConsolidationCompleted,
    ]

    for et in event_types:
        event_bus.subscribe(et, handler)  # type: ignore[arg-type]

    try:
        # Keep alive: read messages (pings, etc.) until disconnect
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _connections[engagement_id].discard(websocket)
        if not _connections[engagement_id]:
            del _connections[engagement_id]
