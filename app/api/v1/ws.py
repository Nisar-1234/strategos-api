"""
WebSocket endpoint — real-time signal delivery.

Clients connect to /api/v1/ws/{conflict_id} and receive JSON messages
whenever a new signal arrives for that conflict or a global ALERT fires.

Redis channels subscribed per connection:
  ws:signal:{conflict_id}   — new signal for this conflict
  ws:convergence:{conflict_id} — convergence score update
  ws:alert                  — any ALERT-severity signal (all conflicts)

Message format (JSON):
  { "type": "signal" | "convergence" | "alert", "data": { ... } }
"""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.config import get_settings

router = APIRouter()
logger = logging.getLogger("strategos.ws")
settings = get_settings()


@router.websocket("/ws/{conflict_id}")
async def websocket_conflict(websocket: WebSocket, conflict_id: str):
    await websocket.accept()
    logger.info("WS client connected for conflict %s", conflict_id)

    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        pubsub = r.pubsub()
        await pubsub.subscribe(
            f"ws:signal:{conflict_id}",
            f"ws:convergence:{conflict_id}",
            "ws:alert",
        )

        async def _listen():
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                channel: str = message["channel"]
                try:
                    data = json.loads(message["data"])
                except (json.JSONDecodeError, TypeError):
                    continue

                if "convergence" in channel:
                    msg_type = "convergence"
                elif channel == "ws:alert":
                    msg_type = "alert"
                else:
                    msg_type = "signal"

                await websocket.send_json({"type": msg_type, "data": data})

        # Run listener; also absorb incoming client pings to keep conn alive
        listen_task = asyncio.create_task(_listen())
        try:
            while True:
                # Receive any client message (pings, etc.) to detect disconnect
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
        except asyncio.TimeoutError:
            # No client message for 30 s — that's fine, keep listening
            pass
        except WebSocketDisconnect:
            pass
        finally:
            listen_task.cancel()
            await pubsub.unsubscribe()
            await r.aclose()

    except ImportError:
        # redis.asyncio not available — send a single error message and close
        await websocket.send_json({"type": "error", "data": {"message": "Redis unavailable"}})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("WS error for conflict %s: %s", conflict_id, exc)
    finally:
        logger.info("WS client disconnected for conflict %s", conflict_id)


@router.websocket("/ws")
async def websocket_global(websocket: WebSocket):
    """Global WebSocket — receives all ALERT signals across all conflicts."""
    await websocket.accept()
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        pubsub = r.pubsub()
        await pubsub.subscribe("ws:alert")

        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                data = json.loads(message["data"])
                await websocket.send_json({"type": "alert", "data": data})
            except (json.JSONDecodeError, WebSocketDisconnect):
                break

        await pubsub.unsubscribe()
        await r.aclose()
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("Global WS error: %s", exc)
