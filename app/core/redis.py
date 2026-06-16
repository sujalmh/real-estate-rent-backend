import redis.asyncio as redis
from app.config import get_settings

settings = get_settings()

async def get_redis_client():
    """Get Redis client instance."""
    client = redis.from_url(
        settings.redis_url, 
        encoding="utf-8", 
        decode_responses=True
    )
    try:
        yield client
    finally:
        await client.close()
