import json
import redis
from etl.config import settings

redis_client = redis.from_url(settings.redis_url, decode_responses=True)


def get_json(key: str):
    raw = redis_client.get(key)
    if raw is None:
        return None
    return json.loads(raw)


def set_json(key: str, value, ttl: int = None):
    raw = json.dumps(value, default=str)
    if ttl:
        redis_client.setex(key, ttl, raw)
    else:
        redis_client.set(key, raw)


def delete_key(key: str):
    redis_client.delete(key)


def delete_pattern(pattern: str):
    for k in redis_client.scan_iter(match=pattern):
        redis_client.delete(k)
