"""
Unit tests for IndicatorPersistence

Tests saving indicators to Redis cache and ClickHouse database.
"""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.indicator_service.persistence import IndicatorPersistence


@pytest.fixture
def mock_db():
    """Mock BaseTimeSeriesDB"""
    db = MagicMock()
    db.insert_indicators = AsyncMock(return_value=5)
    return db


@pytest.fixture
def mock_cache():
    """Mock BaseCacheClient"""
    cache = MagicMock()
    cache.set = AsyncMock()
    cache.get = AsyncMock()
    return cache


@pytest.mark.unit
class TestIndicatorPersistence:
    """Test IndicatorPersistence save operations"""

    @pytest.mark.asyncio
    async def test_save_indicators_success(self, mock_db, mock_cache):
        """Test successful save to both cache and database"""
        persistence = IndicatorPersistence(db=mock_db, cache=mock_cache)

        timestamp = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        indicators = {
            "SMA_20": 50000.0,
            "SMA_50": 49900.0,
            "EMA_12": 50100.0,
            "RSI_14": 55.5,
        }

        await persistence.save_indicators(
            exchange="binance",
            symbol="BTCUSDT",
            timeframe="1m",
            timestamp=timestamp,
            indicators=indicators,
        )

        # Verify cache write called
        mock_cache.set.assert_called_once()

        # Verify database write called
        mock_db.insert_indicators.assert_called_once_with(
            exchange="binance",
            symbol="BTCUSDT",
            timeframe="1m",
            timestamp=timestamp,
            indicators=indicators,
        )

    @pytest.mark.asyncio
    async def test_cache_key_format(self, mock_db, mock_cache):
        """Test cache key formatting"""
        persistence = IndicatorPersistence(db=mock_db, cache=mock_cache)

        timestamp = datetime.now(UTC)
        indicators = {"SMA_20": 50000.0}

        await persistence.save_indicators(
            exchange="binance",
            symbol="BTCUSDT",
            timeframe="1m",
            timestamp=timestamp,
            indicators=indicators,
        )

        # Verify cache key format
        call_args = mock_cache.set.call_args
        cache_key = call_args[0][0]

        assert cache_key == "indicators:binance:BTCUSDT:1m"

    @pytest.mark.asyncio
    async def test_cache_value_format(self, mock_db, mock_cache):
        """Test cache value JSON format"""
        persistence = IndicatorPersistence(db=mock_db, cache=mock_cache)

        timestamp = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        indicators = {"SMA_20": 50000.0, "RSI_14": 55.5}

        await persistence.save_indicators(
            exchange="binance",
            symbol="BTCUSDT",
            timeframe="1m",
            timestamp=timestamp,
            indicators=indicators,
        )

        # Get cache value from call args
        call_args = mock_cache.set.call_args
        cache_value = call_args[0][1]

        # Parse JSON
        data = json.loads(cache_value)

        assert "timestamp" in data
        assert "indicators" in data
        assert data["timestamp"] == timestamp.isoformat()
        assert data["indicators"] == indicators

    @pytest.mark.asyncio
    async def test_cache_ttl_setting(self, mock_db, mock_cache):
        """Test cache TTL is set to 60 seconds"""
        persistence = IndicatorPersistence(db=mock_db, cache=mock_cache)

        timestamp = datetime.now(UTC)
        indicators = {"SMA_20": 50000.0}

        await persistence.save_indicators(
            exchange="binance",
            symbol="BTCUSDT",
            timeframe="1m",
            timestamp=timestamp,
            indicators=indicators,
        )

        # Verify TTL setting
        call_args = mock_cache.set.call_args
        ttl = call_args.kwargs["ttl"]

        assert ttl == timedelta(seconds=60)

    @pytest.mark.asyncio
    async def test_save_empty_indicators(self, mock_db, mock_cache):
        """Test that empty indicators are not saved"""
        persistence = IndicatorPersistence(db=mock_db, cache=mock_cache)

        timestamp = datetime.now(UTC)
        indicators = {}

        await persistence.save_indicators(
            exchange="binance",
            symbol="BTCUSDT",
            timeframe="1m",
            timestamp=timestamp,
            indicators=indicators,
        )

        # Verify nothing was saved
        mock_cache.set.assert_not_called()
        mock_db.insert_indicators.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_failure_does_not_crash(self, mock_db, mock_cache):
        """Test that cache write failure doesn't prevent database write"""
        persistence = IndicatorPersistence(db=mock_db, cache=mock_cache)

        # Mock cache failure
        mock_cache.set.side_effect = Exception("Redis connection error")

        timestamp = datetime.now(UTC)
        indicators = {"SMA_20": 50000.0}

        # Should not raise exception
        await persistence.save_indicators(
            exchange="binance",
            symbol="BTCUSDT",
            timeframe="1m",
            timestamp=timestamp,
            indicators=indicators,
        )

        # Verify database write still called
        mock_db.insert_indicators.assert_called_once()

    @pytest.mark.asyncio
    async def test_database_failure_does_not_crash(self, mock_db, mock_cache):
        """Test that database write failure doesn't crash"""
        persistence = IndicatorPersistence(db=mock_db, cache=mock_cache)

        # Mock database failure
        mock_db.insert_indicators.side_effect = Exception("ClickHouse connection error")

        timestamp = datetime.now(UTC)
        indicators = {"SMA_20": 50000.0}

        # Should not raise exception
        await persistence.save_indicators(
            exchange="binance",
            symbol="BTCUSDT",
            timeframe="1m",
            timestamp=timestamp,
            indicators=indicators,
        )

        # Verify cache write was attempted
        mock_cache.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_from_cache_success(self, mock_db, mock_cache):
        """Test retrieving indicators from cache"""
        persistence = IndicatorPersistence(db=mock_db, cache=mock_cache)

        # Mock cached data
        cached_data = {
            "timestamp": "2024-01-01T12:00:00+00:00",
            "indicators": {"SMA_20": 50000.0, "RSI_14": 55.5},
        }
        mock_cache.get.return_value = json.dumps(cached_data)

        result = await persistence.get_from_cache(
            exchange="binance", symbol="BTCUSDT", timeframe="1m"
        )

        # Verify correct key used
        mock_cache.get.assert_called_once_with("indicators:binance:BTCUSDT:1m")

        # Verify indicators returned
        assert result == {"SMA_20": 50000.0, "RSI_14": 55.5}

    @pytest.mark.asyncio
    async def test_get_from_cache_miss(self, mock_db, mock_cache):
        """Test cache miss returns None"""
        persistence = IndicatorPersistence(db=mock_db, cache=mock_cache)

        # Mock cache miss
        mock_cache.get.return_value = None

        result = await persistence.get_from_cache(
            exchange="binance", symbol="BTCUSDT", timeframe="1m"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_get_from_cache_error(self, mock_db, mock_cache):
        """Test cache read error returns None"""
        persistence = IndicatorPersistence(db=mock_db, cache=mock_cache)

        # Mock cache error
        mock_cache.get.side_effect = Exception("Redis timeout")

        result = await persistence.get_from_cache(
            exchange="binance", symbol="BTCUSDT", timeframe="1m"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_save_multiple_symbols(self, mock_db, mock_cache):
        """Test saving indicators for multiple symbols"""
        persistence = IndicatorPersistence(db=mock_db, cache=mock_cache)

        timestamp = datetime.now(UTC)

        # Save BTC indicators
        await persistence.save_indicators(
            exchange="binance",
            symbol="BTCUSDT",
            timeframe="1m",
            timestamp=timestamp,
            indicators={"SMA_20": 50000.0},
        )

        # Save ETH indicators
        await persistence.save_indicators(
            exchange="binance",
            symbol="ETHUSDT",
            timeframe="1m",
            timestamp=timestamp,
            indicators={"SMA_20": 3000.0},
        )

        # Verify both saved
        assert mock_cache.set.call_count == 2
        assert mock_db.insert_indicators.call_count == 2

        # Verify correct cache keys
        cache_calls = mock_cache.set.call_args_list
        assert cache_calls[0][0][0] == "indicators:binance:BTCUSDT:1m"
        assert cache_calls[1][0][0] == "indicators:binance:ETHUSDT:1m"

    @pytest.mark.asyncio
    async def test_save_multiple_timeframes(self, mock_db, mock_cache):
        """Test saving indicators for multiple timeframes"""
        persistence = IndicatorPersistence(db=mock_db, cache=mock_cache)

        timestamp = datetime.now(UTC)

        # Save 1m timeframe
        await persistence.save_indicators(
            exchange="binance",
            symbol="BTCUSDT",
            timeframe="1m",
            timestamp=timestamp,
            indicators={"SMA_20": 50000.0},
        )

        # Save 5m timeframe
        await persistence.save_indicators(
            exchange="binance",
            symbol="BTCUSDT",
            timeframe="5m",
            timestamp=timestamp,
            indicators={"SMA_20": 50050.0},
        )

        # Verify both saved with different cache keys
        cache_calls = mock_cache.set.call_args_list
        assert cache_calls[0][0][0] == "indicators:binance:BTCUSDT:1m"
        assert cache_calls[1][0][0] == "indicators:binance:BTCUSDT:5m"

    @pytest.mark.asyncio
    async def test_save_multiple_exchanges(self, mock_db, mock_cache):
        """Test saving indicators for multiple exchanges"""
        persistence = IndicatorPersistence(db=mock_db, cache=mock_cache)

        timestamp = datetime.now(UTC)
        indicators = {"SMA_20": 50000.0}

        # Save Binance
        await persistence.save_indicators(
            exchange="binance",
            symbol="BTCUSDT",
            timeframe="1m",
            timestamp=timestamp,
            indicators=indicators,
        )

        # Save Coinbase
        await persistence.save_indicators(
            exchange="coinbase",
            symbol="BTC-USD",
            timeframe="1m",
            timestamp=timestamp,
            indicators=indicators,
        )

        # Verify different cache keys
        cache_calls = mock_cache.set.call_args_list
        assert cache_calls[0][0][0] == "indicators:binance:BTCUSDT:1m"
        assert cache_calls[1][0][0] == "indicators:coinbase:BTC-USD:1m"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
