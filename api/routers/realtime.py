from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from sse_starlette.sse import EventSourceResponse

from deps import require_role, settings
from models import BiUser
from realtime import last_changed_at, subscriber

router = APIRouter()
logger = logging.getLogger(__name__)

AUTH_TIMEOUT = 3.0
HEARTBEAT_INTERVAL = 30.0
ALLOWED_ROLES = {"admin", "ceo", "cfo", "sales_head", "manager"}


async def _event_stream():
    last = last_changed_at()
    yield {"event": "connected", "data": json.dumps({"last_changed_at": last}, default=str)}
    async with subscriber() as queue:
        while True:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield {"event": "metrics_update", "data": json.dumps(message, default=str)}
            except asyncio.TimeoutError:
                yield {"event": "heartbeat", "data": json.dumps({"ts": None})}


@router.get("/metrics")
def metrics_stream(user: BiUser = Depends(require_role("admin", "ceo", "cfo", "sales_head", "manager"))):
    return EventSourceResponse(_event_stream(), media_type="text/event-stream")


async def _validate_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.api_secret_key, algorithms=[settings.algorithm])
        username = payload.get("sub")
        role = payload.get("role")
        if not username or role not in ALLOWED_ROLES:
            return None
        return {"username": username, "role": role}
    except JWTError:
        return None


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    try:
        raw = await asyncio.wait_for(websocket.receive_json(), timeout=AUTH_TIMEOUT)
    except (asyncio.TimeoutError, json.JSONDecodeError):
        await websocket.close(code=4003, reason="Authentication required")
        return

    if not isinstance(raw, dict) or raw.get("type") != "auth":
        await websocket.close(code=4003, reason="First frame must be auth")
        return

    token = raw.get("token")
    user = await _validate_token(token) if isinstance(token, str) else None
    if not user:
        await websocket.close(code=4003, reason="Invalid token")
        return

    last = last_changed_at()
    await websocket.send_json({
        "type": "connected",
        "payload": {"last_changed_at": last},
    })

    async with subscriber() as queue:
        try:
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_INTERVAL)
                except asyncio.TimeoutError:
                    message = {"type": "heartbeat"}
                await websocket.send_json(message)
        except WebSocketDisconnect:
            logger.info("WebSocket client disconnected: %s", user.get("username"))
        except Exception as exc:
            logger.warning("WebSocket error for %s: %s", user.get("username"), exc)
            try:
                await websocket.close(code=1011, reason="Server error")
            except Exception:
                pass
