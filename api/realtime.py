from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import asyncpg
from deps import engine
from sqlalchemy import text
from etl.utils.cache import delete_pattern

logger = logging.getLogger(__name__)

_subscribers: set[asyncio.Queue] = set()
_listen_task: asyncio.Task | None = None

THROTTLE_SECONDS = 2.0


def _notify_all(message: dict) -> None:
    for queue in list(_subscribers):
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            pass


async def _postgres_listener() -> None:
    url = engine.url.render_as_string(hide_password=False).replace("postgresql+psycopg2://", "postgresql://").replace("postgresql+asyncpg://", "postgresql://")
    conn = None
    while True:
        try:
            conn = await asyncpg.connect(url)
            await conn.add_listener("metrics_update", _pg_callback)
            logger.info("Postgres metrics_update listener connected")
            while True:
                await asyncio.sleep(3600)
        except Exception as exc:
            logger.warning("Postgres listener error: %s", exc)
        finally:
            if conn:
                await conn.close()
        await asyncio.sleep(5)


def _pg_callback(connection, pid, channel, payload: str) -> None:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        data = {"raw": payload}
    try:
        delete_pattern("metrics:*")
    except Exception as exc:
        logger.warning("Metrics cache invalidation error: %s", exc)
    _notify_all({"type": "metrics_update", "payload": data})


def _ensure_listener() -> None:
    global _listen_task
    if _listen_task is None or _listen_task.done():
        _listen_task = asyncio.create_task(_postgres_listener())


@asynccontextmanager
async def subscriber() -> AsyncGenerator[asyncio.Queue, None]:
    _ensure_listener()
    queue: asyncio.Queue = asyncio.Queue(maxsize=8)
    _subscribers.add(queue)
    try:
        yield queue
    finally:
        _subscribers.discard(queue)


def last_changed_at() -> str | None:
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT MAX(changed_at) FROM audit_log
            WHERE table_name IN ('fact_transactions', 'fact_expenses')
        """)).fetchone()
        return row[0].isoformat() if row and row[0] else None
