"""
Unit tests for BaseTimeSeriesDB queued interface pattern.

Tests the queue + worker + batching pattern for database clients (ClickHouse):
- Queue initialization with batch configuration
- Enqueue operations for trades
- Batching logic (accumulate until batch_size, then flush)
- Drop rate tracking and panic thresholds
- Sentinel shutdown with partial batch flushing
- Backward compatibility with legacy async methods
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.interfaces.database import BaseTimeSeriesDB


class TestTimeSeriesDB(BaseTimeSeriesDB):
    """Concrete implementation for testing"""

    def __init__(self):
        super().__init__()
        self._insert_trades_mock = AsyncMock(return_value=0)

    async def _insert_trades_impl(self, trades: list[dict]) -> int:
        """Mock implementation"""
        return await self._insert_trades_mock(trades)

    async def query(self, sql, params=None):
        return []

    async def query_candles(self, exchange, symbol, timeframe, start_time, end_time):
        return []

    async def insert_candles(self, candles, timeframe="1m"):
        return len(candles)

    async def insert_indicators(self, indicators):
        return len(indicators)


@pytest.fixture
def mock_settings():
    """Mock settings with default queue config"""
    settings = MagicMock()
    settings.DB_QUEUE_SIZE = 2000
    settings.DB_WORKERS = 3
    settings.DB_BATCH_SIZE = 100
    return settings


@pytest.fixture
async def connected_db(mock_settings):
    """Create and connect a test database client"""
    with patch("config.settings.get_settings", return_value=mock_settings):
        db = TestTimeSeriesDB()
        await db.connect()
        yield db
        await db.close()


@pytest.fixture
async def small_queue_db(mock_settings):
    """Database client with small queue for testing overflow"""
    mock_settings.DB_QUEUE_SIZE = 10
    mock_settings.DB_WORKERS = 1
    mock_settings.DB_BATCH_SIZE = 50

    with patch("config.settings.get_settings", return_value=mock_settings):
        db = TestTimeSeriesDB()
        await db.connect()
        yield db
        await db.close()


class TestBaseTimeSeriesDBInitialization:
    """Test queue, workers, and batching setup"""

    @pytest.mark.asyncio
    async def test_connect_creates_queue_with_batch_config(self, mock_settings):
        """Verify queue and workers created with batch config"""
        mock_settings.DB_QUEUE_SIZE = 2000
        mock_settings.DB_WORKERS = 3
        mock_settings.DB_BATCH_SIZE = 100

        with patch("config.settings.get_settings", return_value=mock_settings):
            db = TestTimeSeriesDB()
            await db.connect()

            try:
                assert db._queue.maxsize == 2000
                assert len(db._worker_tasks) == 3
            finally:
                await db.close()

    @pytest.mark.asyncio
    async def test_connect_without_queue_raises_error(self):
        """Verify enqueue operations before connect() raise RuntimeError"""
        db = TestTimeSeriesDB()

        with pytest.raises(RuntimeError, match="not connected"):
            db.enqueue_trades([{"trade": 1}])


class TestTimeSeriesDBEnqueueTrades:
    """Test enqueue_trades() method"""

    @pytest.mark.asyncio
    async def test_enqueue_trades_returns_count(self, connected_db):
        """Verify enqueue_trades() returns count of queued trades"""
        trades = [
            {
                "timestamp": datetime.now(timezone.utc),
                "exchange": "binance",
                "symbol": "BTC/USDT",
                "price": 50000.0,
            }
            for _ in range(10)
        ]

        count = connected_db.enqueue_trades(trades)

        assert count == 10
        assert connected_db._queue.qsize() == 1  # 1 tuple item ("trades", list)

    @pytest.mark.asyncio
    async def test_enqueue_empty_trades_returns_zero(self, connected_db):
        """Verify empty list returns 0 without queuing"""
        count = connected_db.enqueue_trades([])

        assert count == 0
        assert connected_db._queue.qsize() == 0

    @pytest.mark.asyncio
    async def test_queue_full_drops_trades(self, small_queue_db):
        """Verify queue full drops trades and tracks metrics"""
        # Fill queue
        for i in range(10):
            small_queue_db.enqueue_trades([{"trade": i}])

        # Next enqueue should drop
        count = small_queue_db.enqueue_trades([{"dropped": 1}, {"dropped": 2}])

        assert count == 0  # Dropped
        assert small_queue_db._dropped_trades == 2
        assert len(small_queue_db._trade_drop_rate_window) == 2

    @pytest.mark.asyncio
    async def test_multiple_enqueue_trades_accumulate(self, connected_db):
        """Verify multiple enqueue_trades() calls accumulate in queue"""
        connected_db.enqueue_trades([{"trade": 1}])
        connected_db.enqueue_trades([{"trade": 2}, {"trade": 3}])
        connected_db.enqueue_trades([{"trade": 4}])

        # Should have 3 items in queue (one per enqueue call)
        assert connected_db._queue.qsize() == 3


class TestTimeSeriesDBBatching:
    """Test worker batching behavior"""

    @pytest.mark.asyncio
    async def test_close_flushes_partial_batches(self, connected_db):
        """Verify close() flushes batches even if < batch_size"""
        connected_db._insert_trades_mock.return_value = 30

        # Enqueue 30 trades (< batch_size of 100)
        trades = [{"trade": i} for i in range(30)]
        connected_db.enqueue_trades(trades)

        # Close immediately
        await connected_db.close()

        # Partial batch should have been flushed
        assert connected_db._insert_trades_mock.call_count == 1
        assert len(connected_db._insert_trades_mock.call_args[0][0]) == 30


class TestTimeSeriesDBDropRateTracking:
    """Test drop rate calculation and panic thresholds"""

    @pytest.mark.asyncio
    async def test_drop_rate_window_60_seconds(self, small_queue_db):
        """Verify drop rate window maintains 60-second sliding window"""
        # Fill queue
        for i in range(10):
            small_queue_db.enqueue_trades([{"trade": i}])

        # Drop 5 trades at T=0
        for i in range(5):
            small_queue_db.enqueue_trades([{"dropped": i}])
            time.sleep(0.01)

        assert len(small_queue_db._trade_drop_rate_window) == 5

        # Mock time.time() to be 61 seconds later
        current_time = time.time()
        with patch("time.time", return_value=current_time + 61):
            # Drop another trade
            small_queue_db.enqueue_trades([{"dropped": 99}])

            # Old drops should be removed from window
            assert len(small_queue_db._trade_drop_rate_window) == 1

    @pytest.mark.asyncio
    async def test_dropped_trades_count_accumulates(self, small_queue_db):
        """Verify _dropped_trades accumulates across multiple drops"""
        # Fill queue
        for i in range(10):
            small_queue_db.enqueue_trades([{"trade": i}])

        # Drop 3 batches
        small_queue_db.enqueue_trades([{"dropped": 1}])
        small_queue_db.enqueue_trades([{"dropped": 2}, {"dropped": 3}])
        small_queue_db.enqueue_trades([{"dropped": 4}])

        assert small_queue_db._dropped_trades == 4


class TestTimeSeriesDBWorkers:
    """Test worker pool processing"""

    @pytest.mark.asyncio
    async def test_worker_error_does_not_crash_others(self, connected_db):
        """Verify worker exceptions don't kill other workers"""
        # Make _insert_trades_impl fail once, then always succeed
        error_raised = False

        async def mock_impl(trades):
            nonlocal error_raised
            if not error_raised:
                error_raised = True
                raise Exception("Database connection error")
            return len(trades)

        connected_db._insert_trades_mock.side_effect = mock_impl

        # Enqueue enough trades to trigger multiple batches
        for i in range(3):
            trades = [{"trade": j} for j in range(110)]
            connected_db.enqueue_trades(trades)
            await asyncio.sleep(0.2)

        # First batch failed, but workers should continue
        assert connected_db._insert_trades_mock.call_count >= 2

        # Workers should still be alive
        assert all(not task.done() for task in connected_db._worker_tasks)


class TestTimeSeriesDBShutdown:
    """Test sentinel shutdown with batch flushing"""

    @pytest.mark.asyncio
    async def test_sentinel_flushes_remaining_batches(self, connected_db):
        """Verify sentinel causes workers to flush partial batches"""
        connected_db._insert_trades_mock.return_value = 50

        # Enqueue 50 trades (half a batch)
        trades = [{"trade": i} for i in range(50)]
        connected_db.enqueue_trades(trades)

        # Close (sends sentinel)
        await connected_db.close()

        # Partial batch should be flushed on sentinel
        assert connected_db._insert_trades_mock.call_count == 1
        assert len(connected_db._insert_trades_mock.call_args[0][0]) == 50

    @pytest.mark.asyncio
    async def test_close_sends_sentinels_to_workers(self, connected_db):
        """Verify close() sends sentinel to each worker"""
        await connected_db.close()

        # Queue should be empty (sentinels consumed)
        assert connected_db._queue.qsize() == 0
        # All workers should be done
        assert all(task.done() for task in connected_db._worker_tasks)

    @pytest.mark.asyncio
    async def test_workers_cleared_after_close(self, connected_db):
        """Verify _worker_tasks list is cleared after close()"""
        await connected_db.close()

        assert len(connected_db._worker_tasks) == 0


class TestTimeSeriesDBBackwardCompatibility:
    """Test legacy async methods"""

    @pytest.mark.asyncio
    async def test_insert_trades_calls_enqueue_trades(self, connected_db):
        """Verify legacy insert_trades() calls enqueue_trades()"""
        trades = [{"trade": 1}]
        count = await connected_db.insert_trades(trades)

        assert count == 1
        assert connected_db._queue.qsize() == 1

    @pytest.mark.asyncio
    async def test_insert_trades_preserves_parameters(self, connected_db):
        """Verify insert_trades() passes parameters correctly"""
        connected_db._insert_trades_mock.return_value = 5

        trades = [{"trade": i} for i in range(150)]
        count = await connected_db.insert_trades(trades)

        assert count == 150

        # Wait for batch processing
        await asyncio.sleep(0.5)

        # Should have been batched and inserted
        assert connected_db._insert_trades_mock.call_count >= 1
