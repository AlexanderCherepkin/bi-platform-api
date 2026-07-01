import redis
from etl.config import settings

client = redis.from_url(settings.redis_url, decode_responses=True)
