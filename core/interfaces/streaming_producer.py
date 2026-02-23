import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class BaseStreamProducer(ABC):
    """
    Abstract interface for stream producers (publishing messages)

    NEW (Phase 2 WebSocket Stability): Includes internal queue + worker pool
    to make enqueue_record() non-blocking and prevent WebSocket backpressure.

    Implementations:
    - KafkaStreamProducer (Open-source)
    - KinesisStreamProducer (AWS)
    - PubSubProducer (GCP)
    - EventHubProducer (Azure)

    Architecture:
        WebSocket → Consumer → StreamProcessor → enqueue_record()
                                                      ↓ (put_nowait, fast)
                                                  Queue → Workers → _send_impl() → Kafka
    """

    def __init__(self):
        # Internal queue + workers (lazy init in connect())
        self._queue: asyncio.Queue | None = None
        self._worker_tasks: list[asyncio.Task] = []
        self._dropped_count = 0  # Metric: dropped records due to queue full
        self._drop_rate_window: list[float] = []  # For tracking drop rate

        # Sentinel for clean shutdown (no polling overhead)
        self._SENTINEL = object()

    async def connect(self) -> None:
        """
        Connect to streaming service + start worker pool

        Subclasses should:
        1. Call super().connect() first (creates queue + starts workers)
        2. Then do provider-specific connection
        """
        from config.settings import get_settings

        settings = get_settings()

        # Create queue
        self._queue = asyncio.Queue(maxsize=settings.STREAM_QUEUE_SIZE)

        # Start workers
        for i in range(settings.STREAM_WORKERS):
            task = asyncio.create_task(self._worker(), name=f"stream-worker-{i}")
            self._worker_tasks.append(task)

        logger.info(f"Started {settings.STREAM_WORKERS} stream workers (queue size: {settings.STREAM_QUEUE_SIZE})")

    def enqueue_record(self, stream_name: str, data: dict[str, Any], partition_key: str) -> dict[str, str]:
        """
        Enqueue record for sending (SYNC, NON-BLOCKING)

        This method is FAST (just put_nowait, no await, no I/O).
        Actual sending happens in background workers.

        Args:
            stream_name: Stream/topic name
            data: Record data
            partition_key: Partition key for ordering

        Returns:
            {"status": "queued"} or {"status": "dropped"}
        """
        if not self._queue:
            raise RuntimeError("Stream producer not connected")

        try:
            # Non-blocking enqueue (sync operation)
            self._queue.put_nowait((stream_name, data, partition_key))
            return {"status": "queued"}
        except asyncio.QueueFull:
            # Track drop metrics
            now = time.time()
            self._dropped_count += 1
            self._drop_rate_window.append(now)

            # Keep only last 60 seconds for rate calculation
            cutoff = now - 60
            self._drop_rate_window = [t for t in self._drop_rate_window if t > cutoff]

            drop_rate = len(self._drop_rate_window) / 60  # drops/sec

            # SLO: Panic if drop rate > 10/sec (configurable threshold)
            if drop_rate > 10:
                logger.error(
                    f"🚨 PANIC: Stream drop rate {drop_rate:.1f}/sec exceeds threshold! "
                    f"Queue full, total dropped: {self._dropped_count}"
                )
            else:
                logger.warning(
                    f"Stream queue full, dropping record: {stream_name}/{partition_key} "
                    f"(rate: {drop_rate:.1f}/sec, total: {self._dropped_count})"
                )

            return {"status": "dropped"}

    async def _worker(self) -> None:
        """
        Background worker - consume from queue and send to stream

        Uses sentinel pattern for clean shutdown (no polling overhead).
        Subclasses must implement _send_impl() for actual I/O.
        """
        while True:
            try:
                item = await self._queue.get()

                # Sentinel check (shutdown signal)
                if item is self._SENTINEL:
                    self._queue.task_done()
                    break

                stream_name, data, partition_key = item

                # Call provider-specific send implementation
                await self._send_impl(stream_name, data, partition_key)

                self._queue.task_done()

            except asyncio.CancelledError:
                # Graceful exit on cancel
                break
            except Exception as e:
                logger.error(f"Stream worker error: {e}", exc_info=True)
                # Continue processing (don't break on error)

    @abstractmethod
    async def _send_impl(self, stream_name: str, data: dict[str, Any], partition_key: str) -> None:
        """
        Provider-specific send implementation (Kafka, Kinesis, etc.)

        Called by worker - does actual I/O.
        Subclasses must implement this method.
        """

    async def send_record(
        self, stream_name: str, data: dict[str, Any], partition_key: str
    ) -> dict[str, Any]:
        """
        Legacy async method for backward compatibility

        NEW: Just calls enqueue_record() (sync, non-blocking)
        """
        return self.enqueue_record(stream_name, data, partition_key)

    @abstractmethod
    async def send_batch(self, stream_name: str, records: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Send multiple records in batch (more efficient)

        Args:
            stream_name: Name of the stream/topic
            records: List of records, each with 'data' and 'partition_key'

        Returns:
            Response with success/failure counts
        """

    async def close(self) -> None:
        """
        Stop workers + flush queue + close connection

        Uses sentinel pattern for clean shutdown (no polling, no _running flag).

        Subclasses should call super().close() after provider-specific cleanup.
        """
        # Signal workers to stop by sending sentinel to each
        if self._queue:
            for _ in self._worker_tasks:
                await self._queue.put(self._SENTINEL)

        # Wait for workers to finish gracefully
        # They will process remaining items, then exit on sentinel
        for task in self._worker_tasks:
            try:
                # Give workers reasonable time to drain queue
                await asyncio.wait_for(task, timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("Stream worker didn't finish in 10s, cancelling")
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        self._worker_tasks.clear()

        # Log metrics
        if self._dropped_count > 0:
            logger.warning(
                f"Stream producer dropped {self._dropped_count} records total due to queue full"
            )

        logger.info("✓ Stream workers stopped and queue flushed")
