from abc import ABC, abstractmethod
from datetime import timedelta


class BaseCacheClient(ABC):
    """
    Abstract interface for caching layer

    Implementations:
    - RedisClient (In-memory, persistent)
    - MemcachedClient (In-memory only)
    """

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to cache service"""

    @abstractmethod
    async def get(self, key: str) -> str | None:
        """
        Get value by key

        Args:
            key: Cache key

        Returns:
            Value as string, or None if not found
        """

    @abstractmethod
    async def set(self, key: str, value: str, ttl: timedelta | None = None) -> bool:
        """
        Set key-value with optional TTL

        Args:
            key: Cache key
            value: Value to store (string)
            ttl: Time to live (optional)

        Returns:
            True if successful
        """

    @abstractmethod
    async def hset(self, name: str, key: str, value: str) -> int:
        """
        Set hash field

        Args:
            name: Hash name
            key: Field key
            value: Field value

        Returns:
            Number of fields added
        """

    @abstractmethod
    async def hgetall(self, name: str) -> dict[str, str]:
        """
        Get all hash fields

        Args:
            name: Hash name

        Returns:
            Dictionary of field:value pairs
        """

    @abstractmethod
    async def close(self) -> None:
        """Close connection"""
