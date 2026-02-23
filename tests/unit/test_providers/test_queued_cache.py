"""
Unit tests for BaseCacheClient queued interface pattern.

Tests the queue + worker pattern for cache clients (Redis):
- Queue initialization and worker creation
- Enqueue set operations (with TTL support)
- Drop rate tracking and warning thresholds
- Worker processing and error handling
- Sentinel shutdown pattern
- Backward compatibility with legacy async methods
"""

import asyncio
import logging
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.interfaces.cache import BaseCacheClient


class TestCacheClient(BaseCacheClient):
    """Concrete implementation for testing"""

    def __init__(self):
        super().__init__()
        self._set_mock = AsyncMock(return_value=True)
        self._get_mock = AsyncMock(return_value=None)

    async def _set_impl(self, key: str, value: str, ttl: int | None = None) -> bool:
        """Mock implementation"""
        return await self._set_mock(key, value, ttl)

    async def get(self, key: str) -> str | None:
        """Mock implementation"""
        return await self._get_mock(key)

    async def delete(self, key: str) -> bool:
        return True

    async def exists(self, key: str) -> bool:
        return True

    async def hset(self, key: str, field: str, value: str) -> bool:
        """Mock hash set"""
        return True

    async def hgetall(self, key: str) -> dict[str, str]:
        """Mock hash get all"""
        return {}


@pytest.fixture
def mock_settings():
    """Mock settings with default queue config"""
    settings = MagicMock()
    settings.CACHE_QUEUE_SIZE = 1000
    settings.CACHE_WORKERS = 5
    return settings


@pytest.fixture
async def connected_cache(mock_settings):
    """Create and connect a test cache client"""
    with patch("config.settings.get_settings", return_value=mock_settings):
        cache = TestCacheClient()
        await cache.connect()
        yield cache
        await cache.close()


@pytest.fixture
async def small_queue_cache(mock_settings):
    """Cache client with small queue for testing overflow"""
    mock_settings.CACHE_QUEUE_SIZE = 10
    mock_settings.CACHE_WORKERS = 1

    with patch("config.settings.get_settings", return_value=mock_settings):
        cache = TestCacheClient()
        await cache.connect()
        yield cache
        await cache.close()


class TestBaseCacheClientInitialization:
    """Test queue and worker initialization"""

    @pytest.mark.asyncio
    async def test_connect_creates_queue_and_workers(self, mock_settings):
        """Verify connect() creates queue with correct size and worker count"""
        mock_settings.CACHE_QUEUE_SIZE = 200
        mock_settings.CACHE_WORKERS = 3

        with patch("config.settings.get_settings", return_value=mock_settings):
            cache = TestCacheClient()
            await cache.connect()

            try:
                # Verify queue created
                assert cache._queue is not None
                assert cache._queue.maxsize == 200

                # Verify workers created
                assert len(cache._worker_tasks) == 3
                assert all(not task.done() for task in cache._worker_tasks)
            finally:
                await cache.close()

    @pytest.mark.asyncio
    async def test_connect_without_queue_raises_error(self):
        """Verify enqueue_set() before connect() raises RuntimeError"""
        cache = TestCacheClient()

        with pytest.raises(RuntimeError, match="not connected"):
            cache.enqueue_set("key", "value")


class TestBaseCacheClientEnqueue:
    """Test enqueue_set() method"""

    @pytest.mark.asyncio
    async def test_enqueue_set_success(self, connected_cache):
        """Verify successful enqueue returns True"""
        result = connected_cache.enqueue_set("price:BTC/USDT", "50000")

        assert result is True
        assert connected_cache._queue.qsize() == 1

    @pytest.mark.asyncio
    async def test_enqueue_set_is_sync(self, connected_cache):
        """Verify enqueue_set() is synchronous (no await needed)"""
        import inspect

        # Should be a regular function, not a coroutine
        assert not inspect.iscoroutinefunction(connected_cache.enqueue_set)

        # Can call without await
        result = connected_cache.enqueue_set("key", "value")
        assert result is True

    @pytest.mark.asyncio
    async def test_queue_full_drops_set(self, small_queue_cache):
        """Verify queue full drops set operation and tracks metrics"""
        # Fill queue to max (queue size = 10)
        for i in range(10):
            small_queue_cache.enqueue_set(f"key{i}", f"value{i}")

        # Next enqueue should drop
        result = small_queue_cache.enqueue_set("overflow", "dropped")

        assert result is False
        assert small_queue_cache._dropped_sets == 1
        assert len(small_queue_cache._drop_rate_window) == 1

    @pytest.mark.asyncio
    async def test_enqueue_set_with_ttl(self, connected_cache):
        """Verify TTL parameter is queued correctly"""
        from datetime import timedelta

        result = connected_cache.enqueue_set("key", "value", ttl=timedelta(seconds=300))

        assert result is True
        assert connected_cache._queue.qsize() == 1

        # Verify TTL is in the queued tuple: ("set", key, value, ttl)
        item = connected_cache._queue.get_nowait()
        assert item[0] == "set"
        assert item[1] == "key"
        assert item[2] == "value"
        assert item[3] == timedelta(seconds=300)

    @pytest.mark.asyncio
    async def test_multiple_enqueue_increases_queue_size(self, connected_cache):
        """Verify multiple enqueues accumulate in queue"""
        for i in range(5):
            connected_cache.enqueue_set(f"key{i}", f"value{i}")

        assert connected_cache._queue.qsize() == 5


class TestCacheClientDropRateTracking:
    """Test drop rate calculation and warning thresholds"""

    @pytest.mark.asyncio
    async def test_drop_rate_window_maintains_60_seconds(self, small_queue_cache):
        """Verify drop rate window only keeps last 60 seconds"""
        # Fill queue
        for i in range(10):
            small_queue_cache.enqueue_set(f"k{i}", f"v{i}")

        # Drop 5 operations at T=0
        for i in range(5):
            small_queue_cache.enqueue_set("drop", "value")
            time.sleep(0.01)

        assert len(small_queue_cache._drop_rate_window) == 5

        # Mock time.time() to be 61 seconds later
        current_time = time.time()
        with patch("time.time", return_value=current_time + 61):
            # Drop another operation
            small_queue_cache.enqueue_set("drop2", "value")

            # Old drops should be removed from window
            assert len(small_queue_cache._drop_rate_window) == 1

    @pytest.mark.asyncio
    async def test_drop_tracking_records_all_drops(self, small_queue_cache):
        """Verify all drops are tracked in _dropped_sets"""
        # Fill queue
        for i in range(10):
            small_queue_cache.enqueue_set(f"k{i}", f"v{i}")

        # Give workers a moment to start processing (so queue stays full)
        await asyncio.sleep(0.05)

        # Drop multiple operations
        for i in range(15):
            result = small_queue_cache.enqueue_set(f"drop{i}", "value")
            # Some may queue if workers drain, but we're testing the ones that drop

        # Verify drop tracking worked
        assert small_queue_cache._dropped_sets > 0, "Should have dropped some sets"
        assert len(small_queue_cache._drop_rate_window) > 0, "Should track dropped timestamps"

    @pytest.mark.asyncio
    async def test_dropped_sets_accumulates(self, small_queue_cache):
        """Verify _dropped_sets accumulates across multiple drops"""
        # Fill queue
        for i in range(10):
            small_queue_cache.enqueue_set(f"k{i}", f"v{i}")

        # Drop 3 operations
        for i in range(3):
            small_queue_cache.enqueue_set(f"drop{i}", "value")

        assert small_queue_cache._dropped_sets == 3


class TestCacheClientWorkers:
    """Test worker pool processing"""

    @pytest.mark.asyncio
    async def test_workers_process_queue_items(self, connected_cache):
        """Verify workers call _set_impl() for each queued item"""
        # Configure mock to return success
        connected_cache._set_mock.return_value = True

        # Enqueue 5 operations
        for i in range(5):
            connected_cache.enqueue_set(f"key{i}", f"value{i}")

        # Wait for workers to process
        await connected_cache._queue.join()

        # Verify _set_impl was called 5 times
        assert connected_cache._set_mock.call_count == 5

    @pytest.mark.asyncio
    async def test_worker_passes_ttl_to_impl(self, connected_cache):
        """Verify workers pass TTL parameter to _set_impl()"""
        from datetime import timedelta

        connected_cache._set_mock.return_value = True

        # Enqueue with TTL
        ttl = timedelta(seconds=600)
        connected_cache.enqueue_set("key", "value", ttl=ttl)

        # Wait for processing
        await connected_cache._queue.join()

        # Verify call args include TTL
        args = connected_cache._set_mock.call_args[0]
        assert args[0] == "key"
        assert args[1] == "value"
        assert args[2] == ttl

    @pytest.mark.asyncio
    async def test_worker_error_does_not_crash_others(self, connected_cache):
        """Verify worker exceptions don't kill other workers"""
        # Make _set_impl raise error on first call, then succeed
        connected_cache._set_mock.side_effect = [
            Exception("Connection error"),
            True,
            True,
        ]

        # Enqueue 3 operations
        for i in range(3):
            connected_cache.enqueue_set(f"key{i}", f"value{i}")

        # Wait
        await asyncio.sleep(0.5)

        # First call failed, but workers should continue
        assert connected_cache._set_mock.call_count >= 2

        # All workers should still be alive
        assert all(not task.done() for task in connected_cache._worker_tasks)

    @pytest.mark.asyncio
    async def test_workers_receive_correct_parameters(self, connected_cache):
        """Verify workers pass correct key, value, ttl to _set_impl()"""
        from datetime import timedelta

        connected_cache._set_mock.return_value = True

        # Enqueue specific operation
        ttl = timedelta(seconds=300)
        connected_cache.enqueue_set("price:BTC", "50000", ttl=ttl)

        # Wait for processing
        await connected_cache._queue.join()

        # Verify call args
        args = connected_cache._set_mock.call_args[0]
        assert args[0] == "price:BTC"
        assert args[1] == "50000"
        assert args[2] == ttl


class TestCacheClientShutdown:
    """Test sentinel pattern shutdown"""

    @pytest.mark.asyncio
    async def test_close_sends_sentinels_to_workers(self, connected_cache):
        """Verify close() sends sentinel to each worker"""
        await connected_cache.close()

        # Queue should be empty (sentinels consumed)
        assert connected_cache._queue.qsize() == 0
        # All workers should be done
        assert all(task.done() for task in connected_cache._worker_tasks)

    @pytest.mark.asyncio
    async def test_close_flushes_remaining_items(self, connected_cache):
        """Verify close() processes remaining queued items before exit"""
        connected_cache._set_mock.return_value = True

        # Enqueue 10 operations
        for i in range(10):
            connected_cache.enqueue_set(f"key{i}", f"value{i}")

        # Close immediately
        await connected_cache.close()

        # All items should have been processed before shutdown
        assert connected_cache._set_mock.call_count == 10

    @pytest.mark.asyncio
    async def test_close_timeout_cancels_workers(self):
        """Verify close() cancels workers that don't finish in 5s"""
        mock_settings = MagicMock()
        mock_settings.CACHE_QUEUE_SIZE = 100
        mock_settings.CACHE_WORKERS = 2

        with patch("config.settings.get_settings", return_value=mock_settings):
            cache = TestCacheClient()
            await cache.connect()

            # Mock _set_impl to be very slow
            async def slow_set(*args):
                await asyncio.sleep(10)  # Longer than 5s timeout

            cache._set_mock = slow_set

            # Enqueue item
            cache.enqueue_set("key", "value")

            # Close with timeout (should cancel workers after 5s)
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
                await cache.close()

            # Workers should be cancelled or done
            assert all(task.cancelled() or task.done() for task in cache._worker_tasks)

    @pytest.mark.asyncio
    async def test_workers_cleared_after_close(self, connected_cache):
        """Verify _worker_tasks list is cleared after close()"""
        await connected_cache.close()

        assert len(connected_cache._worker_tasks) == 0

    @pytest.mark.asyncio
    async def test_queue_join_waits_for_completion(self, connected_cache):
        """Verify _queue.join() waits for all items to be processed"""
        connected_cache._set_mock.return_value = True

        # Enqueue 5 operations
        for i in range(5):
            connected_cache.enqueue_set(f"key{i}", f"value{i}")

        # join() should block until all processed
        await connected_cache._queue.join()

        # All items should be processed
        assert connected_cache._set_mock.call_count == 5
        assert connected_cache._queue.qsize() == 0


class TestCacheClientBackwardCompatibility:
    """Test legacy async method compatibility"""

    @pytest.mark.asyncio
    async def test_set_calls_enqueue_set(self, connected_cache):
        """Verify legacy set() calls new enqueue_set()"""
        result = await connected_cache.set("key", "value")

        assert result is True
        assert connected_cache._queue.qsize() == 1

    @pytest.mark.asyncio
    async def test_set_with_ttl_calls_enqueue_set(self, connected_cache):
        """Verify legacy set() with TTL calls enqueue_set() correctly"""
        from datetime import timedelta

        result = await connected_cache.set("key", "value", ttl=timedelta(seconds=300))

        assert result is True
        assert connected_cache._queue.qsize() == 1

        # Verify TTL passed through: ("set", key, value, ttl)
        item = connected_cache._queue.get_nowait()
        assert item[3] == timedelta(seconds=300)

    @pytest.mark.asyncio
    async def test_set_preserves_parameters(self, connected_cache):
        """Verify set() passes parameters correctly to workers"""
        from datetime import timedelta

        connected_cache._set_mock.return_value = True

        ttl = timedelta(seconds=600)
        await connected_cache.set("my-key", "my-value", ttl=ttl)

        # Wait for processing
        await connected_cache._queue.join()

        # Verify parameters passed to worker
        args = connected_cache._set_mock.call_args[0]
        assert args[0] == "my-key"
        assert args[1] == "my-value"
        assert args[2] == ttl
