"""
Unit tests for StreamProcessor

Mocks all dependencies (Stream, Storage, TimeSeriesDB, Cache) to test orchestration logic
"""

import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from core.models.market_data import Trade
from services.market_data_ingestion.stream_processor import StreamProcessor


@pytest.fixture
def mock_clients():
    """Fixture to mock all client dependencies"""
    with (
        patch(
            "services.market_data_ingestion.stream_processor.create_stream_producer"
        ) as mock_stream_factory,
        patch(
            "services.market_data_ingestion.stream_processor.create_storage_client"
        ) as mock_storage_factory,
        patch(
            "services.market_data_ingestion.stream_processor.create_timeseries_db"
        ) as mock_timeseries_factory,
        patch(
            "services.market_data_ingestion.stream_processor.create_cache_client"
        ) as mock_cache_factory,
        patch("services.market_data_ingestion.stream_processor.get_settings") as mock_settings,
    ):
        # Create mock clients
        mock_stream = AsyncMock()
        mock_storage = AsyncMock()
        mock_timeseries = AsyncMock()
        mock_cache = AsyncMock()

        # Factory returns mocks
        mock_stream_factory.return_value = mock_stream
        mock_storage_factory.return_value = mock_storage
        mock_timeseries_factory.return_value = mock_timeseries
        mock_cache_factory.return_value = mock_cache

        # Mock settings
        mock_settings.return_value.STREAM_MARKET_TRADES = "test-stream"
        mock_settings.return_value.S3_BUCKET_RAW_DATA = "test-bucket"

        yield {
            "stream": mock_stream,
            "storage": mock_storage,
            "timeseries": mock_timeseries,
            "cache": mock_cache,
            "settings": mock_settings,
        }


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


class TestStreamProcessorInitialization:
    """Test StreamProcessor initialization"""

    def test_initialization_with_default_buffer(self, mock_clients):
        """Test processor initialization with default buffer size"""
        processor = StreamProcessor()

        assert processor.buffer_size == 100
        assert processor.trade_buffer == []

    def test_initialization_with_custom_buffer(self, mock_clients):
        """Test processor initialization with custom buffer size"""
        processor = StreamProcessor(buffer_size=50)

        assert processor.buffer_size == 50


class TestStreamProcessorConnect:
    """Test connection to downstream services"""

    @pytest.mark.asyncio
    async def test_connect_calls_all_clients(self, mock_clients):
        """Test that connect() calls connect on all clients"""
        processor = StreamProcessor()

        await processor.connect()

        mock_clients["stream"].connect.assert_called_once()
        mock_clients["storage"].connect.assert_called_once()
        mock_clients["timeseries"].connect.assert_called_once()
        mock_clients["cache"].connect.assert_called_once()


class TestStreamProcessorProcessTrade:
    """Test trade processing logic"""

    @pytest.mark.asyncio
    async def test_process_trade_sends_to_stream(self, mock_clients, sample_trade):
        """Test that process_trade sends to stream (Kafka/Kinesis)"""
        processor = StreamProcessor()
        await processor.connect()

        await processor.process_trade(sample_trade)

        mock_clients["stream"].send_record.assert_called_once()
        call_args = mock_clients["stream"].send_record.call_args
        assert call_args[1]["stream_name"] == "test-stream"
        assert call_args[1]["partition_key"] == "BTCUSDT"

    @pytest.mark.asyncio
    async def test_process_trade_buffers_for_timeseries_db(self, mock_clients, sample_trade):
        """Test that trades are buffered before timeseries DB insert"""
        processor = StreamProcessor(buffer_size=3)
        await processor.connect()

        # Process 2 trades (< buffer_size)
        await processor.process_trade(sample_trade)
        await processor.process_trade(sample_trade)

        # Should NOT flush yet
        mock_clients["timeseries"].insert_trades.assert_not_called()
        assert len(processor.trade_buffer) == 2

    @pytest.mark.asyncio
    async def test_process_trade_flushes_when_buffer_full(self, mock_clients, sample_trade):
        """Test that buffer flushes when full"""
        processor = StreamProcessor(buffer_size=3)
        await processor.connect()
        mock_clients["timeseries"].insert_trades.return_value = 3

        # Process 3 trades (= buffer_size)
        await processor.process_trade(sample_trade)
        await processor.process_trade(sample_trade)
        await processor.process_trade(sample_trade)

        # Should flush
        mock_clients["timeseries"].insert_trades.assert_called_once()
        assert len(processor.trade_buffer) == 0  # Buffer cleared

    @pytest.mark.asyncio
    async def test_process_trade_updates_cache(self, mock_clients, sample_trade):
        """Test that process_trade updates cache (Redis/Memcached)"""
        processor = StreamProcessor()
        await processor.connect()

        await processor.process_trade(sample_trade)

        mock_clients["cache"].set.assert_called_once()
        call_args = mock_clients["cache"].set.call_args
        assert "latest_price:binance:BTCUSDT" in call_args[0][0]


class TestStreamProcessorErrorHandling:
    """Test error handling in stream processor"""

    @pytest.mark.asyncio
    async def test_stream_error_does_not_stop_processing(self, mock_clients, sample_trade):
        """Test that stream error doesn't prevent storage/timeseries/cache updates"""
        processor = StreamProcessor(buffer_size=1)
        await processor.connect()

        # Make stream fail
        mock_clients["stream"].send_record.side_effect = Exception("Stream error")
        mock_clients["timeseries"].insert_trades.return_value = 1

        # Should not raise exception
        await processor.process_trade(sample_trade)

        # Storage, timeseries and cache should still be called
        mock_clients["storage"].upload_file.assert_called_once()
        mock_clients["timeseries"].insert_trades.assert_called_once()
        mock_clients["cache"].set.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_error_does_not_stop_processing(self, mock_clients, sample_trade):
        """Test that cache error doesn't prevent stream/storage/timeseries updates"""
        processor = StreamProcessor(buffer_size=1)
        await processor.connect()

        # Make cache fail
        mock_clients["cache"].set.side_effect = Exception("Cache error")
        mock_clients["timeseries"].insert_trades.return_value = 1

        # Should not raise exception
        await processor.process_trade(sample_trade)

        # Stream, storage and timeseries should still be called
        mock_clients["stream"].send_record.assert_called_once()
        mock_clients["storage"].upload_file.assert_called_once()
        mock_clients["timeseries"].insert_trades.assert_called_once()


class TestStreamProcessorClose:
    """Test cleanup and resource closing"""

    @pytest.mark.asyncio
    async def test_close_flushes_remaining_trades(self, mock_clients, sample_trade):
        """Test that close() flushes remaining trades in buffer"""
        processor = StreamProcessor(buffer_size=100)
        await processor.connect()
        mock_clients["timeseries"].insert_trades.return_value = 2

        # Add 2 trades to buffer (< buffer_size)
        await processor.process_trade(sample_trade)
        await processor.process_trade(sample_trade)

        # Close should flush remaining trades
        await processor.close()

        mock_clients["timeseries"].insert_trades.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_calls_all_client_closes(self, mock_clients):
        """Test that close() calls close on all clients"""
        processor = StreamProcessor()
        await processor.connect()

        await processor.close()

        mock_clients["stream"].close.assert_called_once()
        mock_clients["storage"].close.assert_called_once()
        mock_clients["timeseries"].close.assert_called_once()
        mock_clients["cache"].close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_with_empty_buffer(self, mock_clients):
        """Test close when buffer is empty"""
        processor = StreamProcessor()
        await processor.connect()

        # Should not crash with empty buffer
        await processor.close()

        # Should still close all clients
        mock_clients["stream"].close.assert_called_once()


class TestStreamProcessorBatchProcessing:
    """Test batch processing behavior"""

    @pytest.mark.asyncio
    async def test_buffer_accumulation(self, mock_clients, sample_trade):
        """Test that buffer accumulates correctly"""
        processor = StreamProcessor(buffer_size=5)
        await processor.connect()

        # Process 4 trades
        for _ in range(4):
            await processor.process_trade(sample_trade)

        assert len(processor.trade_buffer) == 4
        mock_clients["timeseries"].insert_trades.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_flushes(self, mock_clients, sample_trade):
        """Test multiple buffer flushes"""
        processor = StreamProcessor(buffer_size=2)
        await processor.connect()
        mock_clients["timeseries"].insert_trades.return_value = 2

        # Process 5 trades (should flush twice)
        for _ in range(5):
            await processor.process_trade(sample_trade)

        # 2 flushes (4 trades) + 1 remaining in buffer
        assert mock_clients["timeseries"].insert_trades.call_count == 2
        assert len(processor.trade_buffer) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
