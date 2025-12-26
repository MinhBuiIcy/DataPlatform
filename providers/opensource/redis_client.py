"""
Redis implementation of cache client

Provides fast in-memory caching with persistence
"""

import logging
from datetime import timedelta

from redis.asyncio import Redis

from config.settings import get_settings
from core.interfaces.cache import BaseCacheClient

logger = logging.getLogger(__name__)


class RedisClient(BaseCacheClient):
    """
    Redis implementation

    Features:
    - In-memory storage (microsecond latency)
    - Persistence (RDB + AOF)
    - Data structures (strings, hashes, lists, sets)
    - TTL support
    """

    def __init__(self):
        self.settings = get_settings()
        self.client: Redis | None = None

    async def connect(self) -> None:
        """Connect to Redis"""
        try:
            self.client = Redis.from_url(self.settings.redis_url, decode_responses=True)
            # Test connection
            await self.client.ping()
            logger.info(
                f"✓ Connected to Redis: {self.settings.REDIS_HOST}:{self.settings.REDIS_PORT}"
            )
        except Exception as e:
            logger.error(f"✗ Failed to connect to Redis: {e}")
            raise

    async def get(self, key: str) -> str | None:
        """Get value by key"""
        if not self.client:
            raise RuntimeError("Redis client not connected")

        try:
            return await self.client.get(key)
        except Exception as e:
            logger.error(f"✗ Redis GET error: {e}")
            raise

    async def set(
        self, key: str, value: str, ttl: timedelta | None = None, ex: int | None = None, **kwargs
    ) -> bool:
        """
        Set key-value with optional TTL

        Args:
            key: Redis key
            value: Value to set
            ttl: TTL as timedelta (optional)
            ex: TTL in seconds (optional, takes precedence)
            **kwargs: Additional redis.asyncio.set() parameters
        """
        if not self.client:
            raise RuntimeError("Redis client not connected")

        try:
            # Build kwargs for redis client
            redis_kwargs = kwargs.copy()
            if ex is not None:
                redis_kwargs["ex"] = ex
            elif ttl:
                redis_kwargs["ex"] = int(ttl.total_seconds())

            return await self.client.set(key, value, **redis_kwargs)
        except Exception as e:
            logger.error(f"✗ Redis SET error: {e}")
            raise

    async def hset(self, name: str, key: str, value: str) -> int:
        """Set hash field"""
        if not self.client:
            raise RuntimeError("Redis client not connected")

        try:
            return await self.client.hset(name, key, value)
        except Exception as e:
            logger.error(f"✗ Redis HSET error: {e}")
            raise

    async def hgetall(self, name: str) -> dict[str, str]:
        """Get all hash fields"""
        if not self.client:
            raise RuntimeError("Redis client not connected")

        try:
            return await self.client.hgetall(name)
        except Exception as e:
            logger.error(f"✗ Redis HGETALL error: {e}")
            raise

    async def delete(self, *keys: str) -> int:
        """Delete one or more keys"""
        if not self.client:
            raise RuntimeError("Redis client not connected")

        try:
            return await self.client.delete(*keys)
        except Exception as e:
            logger.error(f"✗ Redis DELETE error: {e}")
            raise

    async def close(self) -> None:
        """Close connection"""
        if self.client:
            await self.client.close()
            logger.info("✓ Redis connection closed")
