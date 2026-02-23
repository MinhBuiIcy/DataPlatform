"""
Redis implementation of cache client

Provides fast in-memory caching with persistence

NEW (Phase 2 WebSocket Stability): Uses queued interface pattern from BaseCacheClient
"""

import logging
from datetime import timedelta

from redis.asyncio import Redis

from config.settings import get_settings
from core.interfaces.cache import BaseCacheClient

logger = logging.getLogger(__name__)


class RedisClient(BaseCacheClient):
    """
    Redis implementation with internal queue + worker pool

    Architecture:
        StreamProcessor → enqueue_set() → Queue → Workers → Redis
                              ↓ (put_nowait, fast)
                          Non-blocking

    Features:
    - Internal queue (1000 items) + worker pool (2 workers)
    - enqueue_set() is FAST (sync put_nowait, no await)
    - Workers handle actual Redis sets in background
    - In-memory storage (microsecond latency)
    - Persistence (RDB + AOF)
    - Data structures (strings, hashes, lists, sets)
    - TTL support
    """

    def __init__(self):
        super().__init__()  # Initialize queue + workers from BaseCacheClient
        self.settings = get_settings()
        self.client: Redis | None = None

    async def connect(self) -> None:
        """Connect to Redis + start worker pool"""
        # Start workers FIRST (BaseCacheClient.connect())
        await super().connect()

        # Then connect to Redis
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

    async def _set_impl(self, key: str, value: str, ttl: timedelta | None) -> None:
        """
        Actual Redis set (called by worker from BaseCacheClient)

        Args:
            key: Redis key
            value: String value
            ttl: Optional TTL as timedelta

        This does the real I/O. Called in background by worker pool.
        """
        if not self.client:
            raise RuntimeError("Redis client not connected")

        try:
            if ttl:
                await self.client.set(key, value, ex=int(ttl.total_seconds()))
            else:
                await self.client.set(key, value)
        except Exception as e:
            logger.error(f"✗ Redis SET error: {e}")
            # Don't raise - worker continues processing other messages

    async def get(self, key: str) -> str | None:
        """Get value by key"""
        if not self.client:
            raise RuntimeError("Redis client not connected")

        try:
            return await self.client.get(key)
        except Exception as e:
            logger.error(f"✗ Redis GET error: {e}")
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
        """Stop workers + close Redis"""
        # Stop workers first (will flush queue) - BaseCacheClient.close()
        await super().close()

        # Then close Redis connection
        if self.client:
            await self.client.close()
            logger.info("✓ Redis connection closed")
