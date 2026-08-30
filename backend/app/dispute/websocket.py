"""
WebSocket endpoint for real-time global dashboard observability.

The Flutter UI connects here to receive system-wide events (dispute
received, node updates, execution completed) as they happen.  Events are
pushed by the webhook background processor — the client never sends data.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter()


class ConnectionManager:
    """Manages a flat list of active global dashboard WebSocket clients."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """Accept a new dashboard client and register it."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(
            "Dashboard client connected — %d active", len(self.active_connections)
        )

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a dashboard client from the pool."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(
            "Dashboard client disconnected — %d active",
            len(self.active_connections),
        )

    async def broadcast_system_event(self, message: dict) -> None:
        """Push an event to every connected dashboard client.

        Silently drops clients whose connections have broken.
        """
        dead: list[WebSocket] = []
        for ws in self.active_connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active_connections.remove(ws)
            logger.warning("Removed dead dashboard connection")

    async def broadcast_metrics_stale(self, scope: str = "daily_summary") -> None:
        """Broadcast a lightweight metrics invalidation signal.

        The frontend reacts by refetching from the REST metrics endpoints
        (e.g. invalidate a React Query / SWR cache key).  The socket
        never carries full metrics payloads — only this small signal.

        Args:
            scope: What changed — ``daily_summary``, ``breakdown``, or ``all``.
        """
        await self.broadcast_system_event({
            "type": "metrics_stale",
            "scope": scope,
        })


# ── Singleton shared across the app ──
manager = ConnectionManager()


@router.websocket("/ws/dashboard")
async def dashboard_stream(websocket: WebSocket):
    """
    Global dashboard WebSocket endpoint.

    Protocol:
      1. Client connects to /ws/dashboard (no ID required).
      2. Server sends an initial ``system_status`` event.
      3. Connection stays open — the server pushes ``dispute_received``,
         ``node_update``, and ``execution_completed`` events as they occur.
      4. Client is not expected to send any payload.
    """
    await manager.connect(websocket)
    try:
        # Confirm the connection with an initial status event
        await websocket.send_json({
            "event": "system_status",
            "status": "connected",
        })

        # Keep the connection alive — we only need to detect disconnects.
        # The client does not send data; we simply wait until the socket
        # closes or an error occurs.
        while True:
            # receive_text will block until the client sends something or
            # disconnects.  We discard any incoming data — it's a
            # server-push-only channel.
            await websocket.receive_text()

    except WebSocketDisconnect:
        logger.info("Dashboard client disconnected gracefully")
    except Exception:
        logger.exception("Unexpected error on dashboard WebSocket")
    finally:
        manager.disconnect(websocket)
