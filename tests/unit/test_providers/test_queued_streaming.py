"""
Unit tests for BaseStreamProducer queued interface pattern.

Tests the queue + worker pattern for streaming clients (Kafka/Kinesis):
- Queue initialization and worker creation
- Enqueue operations (success, overflow, drop tracking)
- Worker processing and error handling
- Sentinel shutdown pattern
- Backward compatibility with legacy async methods
"""

import asyncio
import logging
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.interfaces.streaming_producer import BaseStreamProducer


class TestStreamProducer(BaseStreamProducer):
    """Concrete implementation for testing"""

    def __init__(self):
        super().__init__()
        self._send_impl = AsyncMock()  # Mock the send implementation
        self._send_batch_impl = AsyncMock()

    async def _send_impl(self, topic: str, record: dict, key: str) -> None:
        """Mock implementation that can be configured per test"""
        await self._send_impl(topic, record, key)

    async def send_batch(self, stream_name: str, records: list[dict]) -> dict:
        """Mock batch send implementation"""
        return await self._send_batch_impl(stream_name, records)


@pytest.fixture
def mock_settings():
    """Mock settings with default queue config"""
    settings = MagicMock()
    settings.STREAM_QUEUE_SIZE = 5000
    settings.STREAM_WORKERS = 10
    return settings


@pytest.fixture
async def connected_producer(mock_settings):
    """Create and connect a test producer"""
    with patch("config.settings.get_settings", return_value=mock_settings):
        producer = TestStreamProducer()
        await producer.connect()
        yield producer
        await producer.close()


@pytest.fixture
async def small_queue_producer(mock_settings):
    """Producer with small queue for testing overflow"""
    mock_settings.STREAM_QUEUE_SIZE = 10
    mock_settings.STREAM_WORKERS = 1

    with patch("config.settings.get_settings", return_value=mock_settings):
        producer = TestStreamProducer()
        await producer.connect()
        yield producer
        await producer.close()


@pytest.fixture
async def blocked_queue_producer(mock_settings):
    """Producer with blocked worker to ensure queue stays full"""
    mock_settings.STREAM_QUEUE_SIZE = 10
    mock_settings.STREAM_WORKERS = 1

    with patch("config.settings.get_settings", return_value=mock_settings):
        producer = TestStreamProducer()

        # Make worker block forever on first item
        event = asyncio.Event()
        async def blocked_send(*args):
            await event.wait()  # Never returns

        producer._send_impl.side_effect = blocked_send

        await producer.connect()
        yield producer

        # Unblock workers before cleanup
        event.set()
        await producer.close()


class TestBaseStreamProducerInitialization:
    """Test queue and worker initialization"""

    @pytest.mark.asyncio
    async def test_connect_creates_queue_and_workers(self, mock_settings):
        """Verify connect() creates queue with correct size and worker count"""
        # Mock settings
        mock_settings.STREAM_QUEUE_SIZE = 100
        mock_settings.STREAM_WORKERS = 5

        # Create test producer (concrete implementation for testing)
        with patch("config.settings.get_settings", return_value=mock_settings):
            producer = TestStreamProducer()
            await producer.connect()

            try:
                # Verify queue created
                assert producer._queue is not None
                assert producer._queue.maxsize == 100

                # Verify workers created
                assert len(producer._worker_tasks) == 5
                assert all(not task.done() for task in producer._worker_tasks)
            finally:
                await producer.close()

    @pytest.mark.asyncio
    async def test_connect_without_queue_raises_error(self):
        """Verify enqueue_record() before connect() raises RuntimeError"""
        producer = TestStreamProducer()

        with pytest.raises(RuntimeError, match="not connected"):
            producer.enqueue_record("test-topic", {"data": 1}, "key1")


class TestBaseStreamProducerEnqueue:
    """Test enqueue_record() method"""

    @pytest.mark.asyncio
    async def test_enqueue_record_success(self, connected_producer):
        """Verify successful enqueue returns queued status"""
        result = connected_producer.enqueue_record(
            "test-topic", {"price": 50000}, "BTC/USDT"
        )

        assert result == {"status": "queued"}
        assert connected_producer._queue.qsize() == 1

    @pytest.mark.asyncio
    async def test_enqueue_record_is_sync(self, connected_producer):
        """Verify enqueue_record() is synchronous (no await needed)"""
        import inspect

        # Should be a regular function, not a coroutine
        assert not inspect.iscoroutinefunction(connected_producer.enqueue_record)

        # Can call without await
        result = connected_producer.enqueue_record("topic", {}, "key")
        assert result["status"] == "queued"

    @pytest.mark.asyncio
    async def test_queue_full_drops_record(self, small_queue_producer):
        """Verify QueueFull is caught and drop is tracked"""
        # Fill queue to max (queue size = 10)
        for i in range(10):
            small_queue_producer.enqueue_record("topic", {"i": i}, f"key{i}")

        # Next enqueue should drop
        result = small_queue_producer.enqueue_record("topic", {}, "overflow")

        assert result == {"status": "dropped"}
        assert small_queue_producer._dropped_count == 1
        assert len(small_queue_producer._drop_rate_window) == 1

    @pytest.mark.asyncio
    async def test_multiple_enqueue_increases_queue_size(self, connected_producer):
        """Verify multiple enqueues accumulate in queue"""
        for i in range(5):
            connected_producer.enqueue_record("topic", {"i": i}, f"key{i}")

        assert connected_producer._queue.qsize() == 5


class TestStreamProducerDropRateTracking:
    """Test drop rate calculation and SLO thresholds"""

    @pytest.mark.asyncio
    async def test_drop_rate_window_maintains_60_seconds(self, small_queue_producer):
        """Verify drop rate window only keeps last 60 seconds"""
        # Fill queue
        for i in range(10):
            small_queue_producer.enqueue_record("topic", {}, f"k{i}")

        # Drop 5 messages at T=0
        for i in range(5):
            small_queue_producer.enqueue_record("topic", {}, "drop")
            time.sleep(0.01)  # Slight delay

        assert len(small_queue_producer._drop_rate_window) == 5

        # Mock time.time() to be 61 seconds later
        current_time = time.time()
        with patch("time.time", return_value=current_time + 61):
            # Drop another message
            small_queue_producer.enqueue_record("topic", {}, "drop2")

            # Old drops should be removed from window
            assert len(small_queue_producer._drop_rate_window) == 1

    @pytest.mark.asyncio
    async def test_high_drop_rate_triggers_warning(self, blocked_queue_producer, caplog):
        """Verify queue full drops are logged with rate tracking"""
        # Give worker a moment to pick up first item and block
        blocked_queue_producer.enqueue_record("topic", {}, "initial")
        await asyncio.sleep(0.05)

        # Fill queue to capacity (10 items total capacity, 1 being processed, so 10 more)
        for i in range(10):
            result = blocked_queue_producer.enqueue_record("topic", {}, f"k{i}")
            assert result["status"] == "queued", f"Fill iteration {i} should queue"

        # Capture all log levels
        caplog.set_level(logging.DEBUG)

        # Now try to enqueue more - should drop and log warnings
        for i in range(15):
            result = blocked_queue_producer.enqueue_record("topic", {}, f"drop{i}")
            assert result["status"] == "dropped", f"Expected drop on iteration {i}"

        # Verify warnings were logged with drop rate tracking
        assert "Stream queue full" in caplog.text
        assert "total:" in caplog.text  # Shows total dropped count
        # Verify drop counter increased
        assert blocked_queue_producer._dropped_count == 15

    @pytest.mark.asyncio
    async def test_dropped_count_accumulates(self, small_queue_producer):
        """Verify _dropped_count accumulates across multiple drops"""
        # Fill queue
        for i in range(10):
            small_queue_producer.enqueue_record("topic", {}, f"k{i}")

        # Drop 3 messages
        for i in range(3):
            small_queue_producer.enqueue_record("topic", {}, f"drop{i}")

        assert small_queue_producer._dropped_count == 3


class TestStreamProducerWorkers:
    """Test worker pool processing"""

    @pytest.mark.asyncio
    async def test_workers_process_queue_items(self, connected_producer):
        """Verify workers call _send_impl() for each queued item"""
        # Configure mock to return success
        connected_producer._send_impl.return_value = {"status": "sent"}

        # Enqueue 5 messages
        for i in range(5):
            connected_producer.enqueue_record("topic", {"i": i}, f"key{i}")

        # Wait for workers to process
        await connected_producer._queue.join()

        # Verify _send_impl was called 5 times
        assert connected_producer._send_impl.call_count == 5

    @pytest.mark.asyncio
    async def test_worker_error_does_not_crash_others(self, connected_producer):
        """Verify worker exceptions don't kill other workers"""
        # Make _send_impl raise error on first call, then succeed
        connected_producer._send_impl.side_effect = [
            Exception("Network error"),
            {"status": "sent"},
            {"status": "sent"},
        ]

        # Enqueue 3 messages
        for i in range(3):
            connected_producer.enqueue_record("topic", {"i": i}, f"key{i}")

        # Wait
        await asyncio.sleep(0.5)

        # First call failed, but workers should continue
        # At least 2 more messages should be processed
        assert connected_producer._send_impl.call_count >= 2

        # All workers should still be alive
        assert all(not task.done() for task in connected_producer._worker_tasks)

    @pytest.mark.asyncio
    async def test_workers_receive_correct_parameters(self, connected_producer):
        """Verify workers pass correct topic, record, key to _send_impl()"""
        connected_producer._send_impl.return_value = {"status": "sent"}

        # Enqueue specific message
        connected_producer.enqueue_record("test-topic", {"price": 50000}, "BTC/USDT")

        # Wait for processing
        await connected_producer._queue.join()

        # Verify call args
        args = connected_producer._send_impl.call_args[0]
        assert args[0] == "test-topic"
        assert args[1] == {"price": 50000}
        assert args[2] == "BTC/USDT"


class TestStreamProducerShutdown:
    """Test sentinel pattern shutdown"""

    @pytest.mark.asyncio
    async def test_close_sends_sentinels_to_workers(self, connected_producer):
        """Verify close() sends sentinel to each worker"""
        await connected_producer.close()

        # Queue should have received one sentinel per worker
        # (already consumed, so queue empty)
        assert connected_producer._queue.qsize() == 0
        assert all(task.done() for task in connected_producer._worker_tasks)

    @pytest.mark.asyncio
    async def test_close_flushes_remaining_items(self, connected_producer):
        """Verify close() processes remaining queued items before exit"""
        connected_producer._send_impl.return_value = {"status": "sent"}

        # Enqueue 10 items
        for i in range(10):
            connected_producer.enqueue_record("topic", {"i": i}, f"key{i}")

        # Close immediately (workers still processing)
        await connected_producer.close()

        # All items should have been processed before shutdown
        assert connected_producer._send_impl.call_count == 10

    @pytest.mark.asyncio
    async def test_close_timeout_cancels_workers(self):
        """Verify close() cancels workers that don't finish in 10s"""
        mock_settings = MagicMock()
        mock_settings.STREAM_QUEUE_SIZE = 100
        mock_settings.STREAM_WORKERS = 2

        with patch("config.settings.get_settings", return_value=mock_settings):
            producer = TestStreamProducer()
            await producer.connect()

            # Mock _send_impl to be very slow
            async def slow_send(*args):
                await asyncio.sleep(15)  # Longer than 10s timeout

            producer._send_impl = slow_send

            # Enqueue item
            producer.enqueue_record("topic", {}, "key")

            # Close with timeout (should cancel workers after 10s)
            # Note: This will actually wait 10s in the test
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
                await producer.close()

            # Workers should be cancelled or done
            assert all(task.cancelled() or task.done() for task in producer._worker_tasks)

    @pytest.mark.asyncio
    async def test_workers_cleared_after_close(self, connected_producer):
        """Verify _worker_tasks list is cleared after close()"""
        await connected_producer.close()

        assert len(connected_producer._worker_tasks) == 0

    @pytest.mark.asyncio
    async def test_queue_join_waits_for_completion(self, connected_producer):
        """Verify _queue.join() waits for all items to be processed"""
        connected_producer._send_impl.return_value = {"status": "sent"}

        # Enqueue 5 items
        for i in range(5):
            connected_producer.enqueue_record("topic", {"i": i}, f"key{i}")

        # join() should block until all processed
        await connected_producer._queue.join()

        # All items should be processed
        assert connected_producer._send_impl.call_count == 5
        assert connected_producer._queue.qsize() == 0


class TestStreamProducerBackwardCompatibility:
    """Test legacy async method compatibility"""

    @pytest.mark.asyncio
    async def test_send_record_calls_enqueue_record(self, connected_producer):
        """Verify legacy send_record() calls new enqueue_record()"""
        result = await connected_producer.send_record("topic", {"data": 1}, "key")

        assert result == {"status": "queued"}
        assert connected_producer._queue.qsize() == 1

    @pytest.mark.asyncio
    async def test_send_record_preserves_parameters(self, connected_producer):
        """Verify send_record() passes parameters correctly"""
        await connected_producer.send_record("my-topic", {"value": 123}, "my-key")

        # Wait for processing
        connected_producer._send_impl.return_value = {"status": "sent"}
        await connected_producer._queue.join()

        # Verify parameters passed to worker
        args = connected_producer._send_impl.call_args[0]
        assert args[0] == "my-topic"
        assert args[1] == {"value": 123}
        assert args[2] == "my-key"
