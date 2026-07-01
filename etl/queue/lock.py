import time
from etl.queue.redis_client import client

LOCK_KEY = "etl:sync:lock"
LOCK_TTL_SECONDS = 600


def acquire_lock() -> bool:
    token = str(time.time())
    acquired = client.set(LOCK_KEY, token, nx=True, ex=LOCK_TTL_SECONDS)
    return acquired is not None


def release_lock() -> None:
    client.delete(LOCK_KEY)
