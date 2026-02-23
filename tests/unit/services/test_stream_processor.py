"""
Unit tests for StreamProcessor (Phase 2 - Redis ONLY)

Tests simplified Redis-only functionality.
"""

import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from core.models.market_data import OrderBook, Trade
from services.market_data_ingestion.stream_processor import StreamProcessor


@pytest.fixture
def mock_cache_client():
    """Fixture to mock Redis cache client"""
    mock_cache = AsyncMock()
    mock_cache.connect = AsyncMock()
    mock_cache.set = AsyncMock()
    mock_cache.close = AsyncMock()
    return mock_cache


@pytest.fixture
def sample_trade():
    """Fixture to create sample trade"""
    return Trade(
        timestamp=datetime(2023, 12, 18, 10, 0, 0, tzinfo=UTC),
        exchange="binance",
        symbol="BTCUSDT",
        trade_id="12345",
        price=Decimal("50000.00"),
        quantity=Decimal("0.1"),
        side="buy",
        is_buyer_maker=False,
    )


@pytest.fixture
def sample_orderbook():
    """Fixture to create sample orderbook"""
    return OrderBook(
        timestamp=datetime(2023, 12, 18, 10, 0, 0, tzinfo=UTC),
        exchange="binance",
        symbol="BTCUSDT",
        bids=[
            (Decimal("49999.00"), Decimal("1.5")),
            (Decimal("49998.00"), Decimal("2.0")),
        ],
        asks=[
            (Decimal("50001.00"), Decimal("1.2")),
            (Decimal("50002.00"), Decimal("1.8")),
        ],
    )


class TestStreamProcessorInitialization:
    """Test StreamProcessor initialization"""

    def test_initialization_redis_only(self, mock_cache_client):
        """Test processor initialization with cache client only"""
        processor = StreamProcessor(cache_client=mock_cache_client)

        assert processor.cache_client == mock_cache_client
        # Verify NO other clients exist
        assert not hasattr(processor, "stream_client")
        assert not hasattr(processor, "storage_client")
        assert not hasattr(processor, "db_client")
        assert not hasattr(processor, "trade_buffer")


class TestStreamProcessorConnect:
    """Test connection to Redis"""

    @pytest.mark.asyncio
    async def test_connect_calls_cache_client(self, mock_cache_client):
        """Test that connect() calls cache client connect"""
        processor = StreamProcessor(cache_client=mock_cache_client)

        await processor.connect()

        mock_cache_client.connect.assert_called_once()


class TestStreamProcessorProcessTrade:
    """Test trade processing logic (Redis only)"""

    @pytest.mark.asyncio
    async def test_process_trade_updates_cache(self, mock_cache_client, sample_trade):
        """Test that process_trade ONLY updates Redis cache"""
        processor = StreamProcessor(cache_client=mock_cache_client)
        await processor.connect()

        await processor.process_trade(sample_trade)

        # Verify Redis cache was updated
        mock_cache_client.set.assert_called_once()
        call_args = mock_cache_client.set.call_args

        # Check key format: latest_price:{exchange}:{symbol}
        assert call_args[0][0] == "latest_price:binance:BTCUSDT"

        # Check value is price as string
        assert call_args[0][1] == "50000.00"

        # Check TTL
        assert call_args[1]["ttl"] == timedelta(seconds=60)

    @pytest.mark.asyncio
    async def test_process_trade_does_not_write_to_clickhouse(
        self, mock_cache_client, sample_trade
    ):
        """Verify StreamProcessor does NOT have ClickHouse client"""
        processor = StreamProcessor(cache_client=mock_cache_client)

        # Should not have db_client attribute
        assert not hasattr(processor, "db_client")
        assert not hasattr(processor, "timeseries_db")

    @pytest.mark.asyncio
    async def test_process_trade_does_not_send_to_stream(self, mock_cache_client, sample_trade):
        """Verify StreamProcessor does NOT have stream client"""
        processor = StreamProcessor(cache_client=mock_cache_client)

        # Should not have stream_client attribute
        assert not hasattr(processor, "stream_client")

    @pytest.mark.asyncio
    async def test_process_trade_does_not_batch(self, mock_cache_client, sample_trade):
        """Verify StreamProcessor does NOT have batch buffers"""
        processor = StreamProcessor(cache_client=mock_cache_client)

        # Should not have buffer attributes
        assert not hasattr(processor, "trade_buffer")
        assert not hasattr(processor, "orderbook_buffer")


class TestStreamProcessorProcessOrderbook:
    """Test orderbook processing logic (Redis only)"""

    @pytest.mark.asyncio
    async def test_process_orderbook_updates_cache(self, mock_cache_client, sample_orderbook):
        """Test that process_orderbook updates Redis cache"""
        processor = StreamProcessor(cache_client=mock_cache_client)
        await processor.connect()

        await processor.process_orderbook(sample_orderbook)

        # Verify Redis cache was updated
        mock_cache_client.set.assert_called_once()
        call_args = mock_cache_client.set.call_args

        # Check key format: orderbook:{exchange}:{symbol}
        assert call_args[0][0] == "orderbook:binance:BTCUSDT"

        # Check data structure
        data = call_args[0][1]
        assert "best_bid_price" in data
        assert "best_ask_price" in data
        assert "spread" in data
        assert "mid_price" in data

        # Check TTL
        assert call_args[1]["ttl"] == timedelta(seconds=60)


class TestStreamProcessorClose:
    """Test cleanup and resource closing"""

    @pytest.mark.asyncio
    async def test_close_calls_cache_close(self, mock_cache_client):
        """Test that close() calls cache client close"""
        processor = StreamProcessor(cache_client=mock_cache_client)
        await processor.connect()

        await processor.close()

        mock_cache_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_does_not_flush_buffers(self, mock_cache_client):
        """Verify close() does NOT flush buffers (no batching in Phase 2)"""
        processor = StreamProcessor(cache_client=mock_cache_client)

        # Should not have flush methods
        assert not hasattr(processor, "_flush_trades")
        assert not hasattr(processor, "_flush_orderbooks")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
