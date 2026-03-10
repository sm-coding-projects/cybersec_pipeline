"""WebSocket endpoint for real-time scan updates.

Subscribes to Redis pub/sub channel ``scan_events:{scan_id}`` and forwards
all events to connected WebSocket clients.  The pipeline engine (running in
a Celery worker) publishes events to the same Redis channel.
"""

from __future__ import annotations

import asyncio
import json
import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import settings
from app.core.websocket_manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/scans/{scan_id}")
async def websocket_scan_events(websocket: WebSocket, scan_id: int) -> None:
    """WebSocket endpoint that streams real-time scan events to the browser.

    1. Accepts the WebSocket connection and registers it with the manager.
    2. Subscribes to Redis pub/sub channel ``scan_events:{scan_id}``.
    3. Forwards every Redis message to all connected WebSocket clients.
    4. Cleans up on disconnect.
    """
    await ws_manager.connect(scan_id, websocket)
    logger.info("WebSocket client connected for scan %d", scan_id)

    redis_client: aioredis.Redis | None = None
    pubsub: aioredis.client.PubSub | None = None

    try:
        # Connect to Redis and subscribe to the scan events channel
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        pubsub = redis_client.pubsub()
        channel = f"scan_events:{scan_id}"
        await pubsub.subscribe(channel)
        logger.info("Subscribed to Redis channel %s", channel)

        # Run two concurrent tasks:
        # 1. Listen for Redis pub/sub messages and forward to WebSocket
        # 2. Listen for WebSocket messages (to detect disconnect)
        await asyncio.gather(
            _redis_listener(pubsub, scan_id),
            _websocket_receiver(websocket, scan_id),
        )

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected for scan %d", scan_id)
    except Exception:
        logger.exception("WebSocket error for scan %d", scan_id)
    finally:
        # Clean up
        await ws_manager.disconnect(scan_id, websocket)

        if pubsub is not None:
            try:
                await pubsub.unsubscribe(f"scan_events:{scan_id}")
                await pubsub.aclose()
            except Exception:
                pass

        if redis_client is not None:
            try:
                await redis_client.aclose()
            except Exception:
                pass

        logger.info("WebSocket cleanup complete for scan %d", scan_id)


async def _redis_listener(pubsub: aioredis.client.PubSub, scan_id: int) -> None:
    """Listen for messages on the Redis pub/sub channel and broadcast them.

    This runs concurrently with the WebSocket receiver.  When a message
    arrives from Redis, it is forwarded to all WebSocket clients watching
    this scan.
    """
    async for message in pubsub.listen():
        if message["type"] != "message":
            continue

        try:
            data = message["data"]
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            event_data = json.loads(data)
            event_name = event_data.get("event", "unknown")
            event_payload = event_data.get("data", {})

            await ws_manager.broadcast(scan_id, event_name, event_payload)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON from Redis for scan %d: %s", scan_id, message["data"])
        except Exception:
            logger.exception("Error processing Redis message for scan %d", scan_id)


async def _websocket_receiver(websocket: WebSocket, scan_id: int) -> None:
    """Receive messages from the WebSocket client.

    The primary purpose is to detect disconnections.  We don't expect
    meaningful messages from the client, but we keep the receive loop
    alive so that ``WebSocketDisconnect`` is raised when the client
    drops the connection, which cancels the ``asyncio.gather``.
    """
    try:
        while True:
            # Wait for any message; mainly to detect disconnect
            data = await websocket.receive_text()
            # Client can send a ping or other message; we just ignore it
            logger.debug("Received WebSocket message from client for scan %d: %s", scan_id, data[:100])
    except WebSocketDisconnect:
        raise
    except Exception:
        pass
