import asyncio
import logging
import time
from abc import ABC, abstractmethod
from datetime import timedelta

logger = logging.getLogger(__name__)


class BaseCacheClient(ABC):
    """
    Abstract interface for caching layer

    NEW (Phase 2 WebSocket Stability): Includes internal queue + worker pool
    to make enqueue_set() non-blocking.

    Implementations:
    - RedisClient (In-memory, persistent)
    - MemcachedClient (In-memory only)

    Architecture:
        StreamProcessor → enqueue_set() → Queue → Workers → Redis
                              ↓ (put_nowait, fast)
                          Non-blocking
    """

    def __init__(self):
        # Internal queue + workers
        self._queue: asyncio.Queue | None = None
        self._worker_tasks: list[asyncio.Task] = []
        self._dropped_sets = 0  # Metric: dropped sets due to queue full
        self._drop_rate_window: list[float] = []  # For drop rate tracking

        # Sentinel for shutdown
        self._SENTINEL = object()

    async def connect(self) -> None:
        """
        Connect to cache service + start worker pool

        Subclasses should:
        1. Call super().connect() first
        2. Then do provider-specific connection
        """
        from config.settings import get_settings

        settings = get_settings()

        # Create queue
        self._queue = asyncio.Queue(maxsize=settings.CACHE_QUEUE_SIZE)

        # Start workers
        for i in range(settings.CACHE_WORKERS):
            task = asyncio.create_task(self._worker(), name=f"cache-worker-{i}")
            self._worker_tasks.append(task)

        logger.info(
            f"Started {settings.CACHE_WORKERS} cache workers (queue size: {settings.CACHE_QUEUE_SIZE})"
        )

    def enqueue_set(self, key: str, value: str, ttl_seconds: int | None = None) -> bool:
        """
        Enqueue cache set operation (SYNC, NON-BLOCKING)

        This method is FAST (just put_nowait, no await, no I/O).

        Args:
            key: Cache key
            value: Value to set
            ttl_seconds: Optional TTL in seconds (int), not timedelta

        Returns:
            True if queued, False if dropped
        """
        if not self._queue:
            raise RuntimeError("Cache client not connected")

        try:
            self._queue.put_nowait(("set", key, value, ttl_seconds))
            return True
        except asyncio.QueueFull:
            # Track drop metrics + rate
            now = time.time()
            self._dropped_sets += 1
            self._drop_rate_window.append(now)

            # Keep only last 60 seconds
            cutoff = now - 60
            self._drop_rate_window = [t for t in self._drop_rate_window if t > cutoff]
            drop_rate = len(self._drop_rate_window) / 60

            # SLO: Cache drops are OK (nice-to-have), just warn at high rate
            if drop_rate > 50:
                logger.warning(
                    f"Cache drop rate high: {drop_rate:.1f}/sec (key: {key}, total: {self._dropped_sets})"
                )
            # No logging for low drop rates (cache drops are acceptable)
            return False

    async def _worker(self) -> None:
        """
        Background worker - consume and set cache

        Uses sentinel pattern for clean shutdown.
        """
        while True:
            try:
                item = await self._queue.get()

                # Sentinel check (shutdown signal)
                if item is self._SENTINEL:
                    self._queue.task_done()
                    break

                operation, key, value, ttl = item

                if operation == "set":
                    await self._set_impl(key, value, ttl)

                self._queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cache worker error: {e}", exc_info=True)

    @abstractmethod
    async def _set_impl(self, key: str, value: str, ttl: timedelta | None) -> None:
        """
        Provider-specific set implementation

        Called by worker - does actual I/O.
        """

    @abstractmethod
    async def get(self, key: str) -> str | None:
        """
        Get value by key

        Args:
            key: Cache key

        Returns:
            Value as string, or None if not found
        """

    async def set(self, key: str, value: str, ttl_seconds: int | None = None) -> bool:
        """
        Set key-value with optional TTL.

        Args:
            key: Cache key
            value: String value
            ttl_seconds: TTL in seconds (int), not timedelta

        Note: Queues operation for background worker (non-blocking)
        """
        return self.enqueue_set(key, value, ttl_seconds)

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

    async def close(self) -> None:
        """
        Stop workers + flush queue

        Uses sentinel pattern for clean shutdown.
        """
        # Signal workers to stop by sending sentinel to each
        if self._queue:
            for _ in self._worker_tasks:
                await self._queue.put(self._SENTINEL)

        # Wait for workers to finish
        for task in self._worker_tasks:
            try:
                await asyncio.wait_for(task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("Cache worker didn't finish in 5s, cancelling")
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        self._worker_tasks.clear()

        # Log metrics (only if significant drops)
        if self._dropped_sets > 100:
            logger.info(f"Cache dropped {self._dropped_sets} sets total (acceptable)")

        logger.info("✓ Cache workers stopped")
