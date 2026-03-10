import json
import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages WebSocket connections per scan.

    Tracks active connections grouped by scan_id and provides
    broadcast capabilities so the pipeline can push real-time
    events to all clients watching a particular scan.
    """

    def __init__(self) -> None:
        self.connections: dict[int, list[WebSocket]] = {}

    async def connect(self, scan_id: int, websocket: WebSocket) -> None:
        """Accept a WebSocket connection and register it for the given scan."""
        await websocket.accept()
        if scan_id not in self.connections:
            self.connections[scan_id] = []
        self.connections[scan_id].append(websocket)
        logger.info("WebSocket connected for scan %d (total: %d)", scan_id, len(self.connections[scan_id]))

    async def disconnect(self, scan_id: int, websocket: WebSocket) -> None:
        """Remove a WebSocket connection from the scan's connection list."""
        if scan_id in self.connections:
            try:
                self.connections[scan_id].remove(websocket)
            except ValueError:
                pass
            if not self.connections[scan_id]:
                del self.connections[scan_id]
            logger.info("WebSocket disconnected for scan %d", scan_id)

    async def broadcast(self, scan_id: int, event: str, data: dict) -> None:
        """Send an event to all clients watching a scan."""
        message = json.dumps({"event": event, "data": data})
        if scan_id not in self.connections:
            return

        dead: list[WebSocket] = []
        for ws in self.connections[scan_id]:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)

        for ws in dead:
            try:
                self.connections[scan_id].remove(ws)
            except ValueError:
                pass

        if scan_id in self.connections and not self.connections[scan_id]:
            del self.connections[scan_id]

    def active_connections(self, scan_id: int) -> int:
        """Return the number of active connections for a scan."""
        return len(self.connections.get(scan_id, []))


# Singleton instance used across the application
ws_manager = WebSocketManager()
