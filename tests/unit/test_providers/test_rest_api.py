"""
Unit tests for exchange REST API clients

Tests BinanceRestAPI, CoinbaseRestAPI, KrakenRestAPI using mocked ccxt responses.
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.models.market_data import Candle
from providers.binance.rest_api import BinanceRestAPI
from providers.coinbase.rest_api import CoinbaseRestAPI
from providers.kraken.rest_api import KrakenRestAPI


@pytest.fixture
def mock_ccxt_binance():
    """Mock ccxt.binance client"""
    with patch("providers.binance.rest_api.ccxt.binance") as mock:
        client = MagicMock()
        client.fetch_ohlcv = AsyncMock()
        client.close = AsyncMock()
        mock.return_value = client
        yield client


@pytest.fixture
def mock_ccxt_coinbase():
    """Mock ccxt.coinbase client"""
    with patch("providers.coinbase.rest_api.ccxt.coinbase") as mock:
        client = MagicMock()
        client.fetch_ohlcv = AsyncMock()
        client.close = AsyncMock()
        mock.return_value = client
        yield client


@pytest.fixture
def mock_ccxt_kraken():
    """Mock ccxt.kraken client"""
    with patch("providers.kraken.rest_api.ccxt.kraken") as mock:
        client = MagicMock()
        client.fetch_ohlcv = AsyncMock()
        client.close = AsyncMock()
        mock.return_value = client
        yield client


def create_mock_ohlcv_data(count=5, start_timestamp_ms=1704067200000):
    """
    Create mock OHLCV data from ccxt.

    Format: [[timestamp_ms, open, high, low, close, volume], ...]
    """
    data = []
    for i in range(count):
        timestamp = start_timestamp_ms + (i * 60000)  # 1 minute apart
        data.append(
            [
                timestamp,
                50000.0 + i * 10,  # open
                50100.0 + i * 10,  # high
                49900.0 + i * 10,  # low
                50050.0 + i * 10,  # close
                100.0 + i,  # volume
            ]
        )
    return data


@pytest.mark.unit
class TestBinanceRestAPI:
    """Test Binance REST API client"""

    @pytest.mark.asyncio
    async def test_fetch_latest_klines_success(self, mock_ccxt_binance):
        """Test fetch_latest_klines with successful API response"""
        # Setup mock response
        mock_data = create_mock_ohlcv_data(count=5)
        mock_ccxt_binance.fetch_ohlcv.return_value = mock_data

        # Create API client
        api = BinanceRestAPI()

        # Fetch klines
        candles = await api.fetch_latest_klines(
            symbol="BTC/USDT", timeframe="1m", limit=5
        )

        # Verify API was called correctly
        mock_ccxt_binance.fetch_ohlcv.assert_called_once_with(
            "BTC/USDT", "1m", limit=5
        )

        # Verify candles returned
        assert len(candles) == 5
        assert all(isinstance(c, Candle) for c in candles)

        # Verify first candle
        first_candle = candles[0]
        assert first_candle.exchange == "binance"
        assert first_candle.symbol == "BTC/USDT"
        assert first_candle.timeframe == "1m"
        assert first_candle.open == Decimal("50000.0")
        assert first_candle.high == Decimal("50100.0")
        assert first_candle.low == Decimal("49900.0")
        assert first_candle.close == Decimal("50050.0")
        assert first_candle.volume == Decimal("100.0")
        assert first_candle.is_synthetic is False

    @pytest.mark.asyncio
    async def test_fetch_klines_with_date_range(self, mock_ccxt_binance):
        """Test fetch_klines with start/end dates"""
        mock_data = create_mock_ohlcv_data(count=10)
        mock_ccxt_binance.fetch_ohlcv.return_value = mock_data

        api = BinanceRestAPI()

        start = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2024, 1, 1, 0, 5, 0, tzinfo=timezone.utc)

        candles = await api.fetch_klines(
            symbol="BTC/USDT", timeframe="1m", start=start, end=end, limit=10
        )

        # Verify API called with correct timestamp
        expected_since = int(start.timestamp() * 1000)
        mock_ccxt_binance.fetch_ohlcv.assert_called_once_with(
            "BTC/USDT", "1m", since=expected_since, limit=10
        )

        assert len(candles) > 0

    @pytest.mark.asyncio
    async def test_fetch_klines_filters_by_end_time(self, mock_ccxt_binance):
        """Test that fetch_klines filters out candles after end time"""
        # Create mock data with timestamps beyond end time
        mock_data = create_mock_ohlcv_data(count=10, start_timestamp_ms=1704067200000)
        mock_ccxt_binance.fetch_ohlcv.return_value = mock_data

        api = BinanceRestAPI()

        start = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2024, 1, 1, 0, 3, 0, tzinfo=timezone.utc)  # Only first 3 candles

        candles = await api.fetch_klines(
            symbol="BTC/USDT", timeframe="1m", start=start, end=end, limit=10
        )

        # Should filter to only candles before end time
        assert all(c.timestamp <= end for c in candles)

    @pytest.mark.asyncio
    async def test_fetch_latest_klines_api_error(self, mock_ccxt_binance):
        """Test error handling when API fails"""
        # Mock API failure
        mock_ccxt_binance.fetch_ohlcv.side_effect = Exception("API rate limit exceeded")

        api = BinanceRestAPI()

        with pytest.raises(Exception, match="API rate limit exceeded"):
            await api.fetch_latest_klines(symbol="BTC/USDT", timeframe="1m")

    @pytest.mark.asyncio
    async def test_candle_creation_from_ohlcv(self, mock_ccxt_binance):
        """Test Candle object creation from OHLCV data"""
        mock_data = [
            [
                1704067200000,  # timestamp
                50000.123456,  # open
                50200.987654,  # high
                49800.111111,  # low
                50100.555555,  # close
                123.456789,  # volume
            ]
        ]
        mock_ccxt_binance.fetch_ohlcv.return_value = mock_data

        api = BinanceRestAPI()
        candles = await api.fetch_latest_klines(symbol="BTC/USDT", timeframe="1m", limit=1)

        candle = candles[0]

        # Verify Decimal precision preserved
        assert candle.open == Decimal("50000.123456")
        assert candle.high == Decimal("50200.987654")
        assert candle.low == Decimal("49800.111111")
        assert candle.close == Decimal("50100.555555")
        assert candle.volume == Decimal("123.456789")

        # Verify quote_volume calculated
        expected_quote_volume = Decimal("123.456789") * Decimal("50100.555555")
        assert abs(candle.quote_volume - expected_quote_volume) < Decimal("0.01")

    @pytest.mark.asyncio
    async def test_close_client(self, mock_ccxt_binance):
        """Test closing ccxt client"""
        api = BinanceRestAPI()
        await api.close()

        mock_ccxt_binance.close.assert_called_once()

    def test_get_supported_timeframes(self):
        """Test supported timeframes for Binance"""
        api = BinanceRestAPI()
        timeframes = api.get_supported_timeframes()

        assert "1m" in timeframes
        assert "5m" in timeframes
        assert "1h" in timeframes
        assert "1d" in timeframes


@pytest.mark.unit
class TestCoinbaseRestAPI:
    """Test Coinbase REST API client"""

    @pytest.mark.asyncio
    async def test_fetch_latest_klines_success(self, mock_ccxt_coinbase):
        """Test Coinbase fetch_latest_klines"""
        mock_data = create_mock_ohlcv_data(count=3)
        mock_ccxt_coinbase.fetch_ohlcv.return_value = mock_data

        api = CoinbaseRestAPI()
        candles = await api.fetch_latest_klines(symbol="BTC/USD", timeframe="1m", limit=3)

        assert len(candles) == 3
        assert candles[0].exchange == "coinbase"
        assert candles[0].symbol == "BTC/USD"

    @pytest.mark.asyncio
    async def test_fetch_klines_with_date_range(self, mock_ccxt_coinbase):
        """Test Coinbase fetch_klines with date range"""
        mock_data = create_mock_ohlcv_data(count=5)
        mock_ccxt_coinbase.fetch_ohlcv.return_value = mock_data

        api = CoinbaseRestAPI()

        start = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2024, 1, 1, 1, 0, 0, tzinfo=timezone.utc)

        candles = await api.fetch_klines(
            symbol="BTC/USD", timeframe="1m", start=start, end=end
        )

        assert len(candles) > 0

    def test_get_supported_timeframes(self):
        """Test Coinbase supported timeframes"""
        api = CoinbaseRestAPI()
        timeframes = api.get_supported_timeframes()

        assert "1m" in timeframes
        assert "5m" in timeframes
        assert "1h" in timeframes
        assert "1d" in timeframes


@pytest.mark.unit
class TestKrakenRestAPI:
    """Test Kraken REST API client"""

    @pytest.mark.asyncio
    async def test_fetch_latest_klines_success(self, mock_ccxt_kraken):
        """Test Kraken fetch_latest_klines"""
        mock_data = create_mock_ohlcv_data(count=3)
        mock_ccxt_kraken.fetch_ohlcv.return_value = mock_data

        api = KrakenRestAPI()
        candles = await api.fetch_latest_klines(symbol="BTC/USD", timeframe="1m", limit=3)

        assert len(candles) == 3
        assert candles[0].exchange == "kraken"
        assert candles[0].symbol == "BTC/USD"

    @pytest.mark.asyncio
    async def test_error_handling(self, mock_ccxt_kraken):
        """Test Kraken error handling"""
        mock_ccxt_kraken.fetch_ohlcv.side_effect = Exception("Kraken API error")

        api = KrakenRestAPI()

        with pytest.raises(Exception, match="Kraken API error"):
            await api.fetch_latest_klines(symbol="BTC/USD", timeframe="1m")

    def test_get_supported_timeframes(self):
        """Test Kraken supported timeframes"""
        api = KrakenRestAPI()
        timeframes = api.get_supported_timeframes()

        assert "1m" in timeframes
        assert "5m" in timeframes
        assert "1h" in timeframes
        assert "1d" in timeframes
        assert "1w" in timeframes


@pytest.mark.unit
class TestRestAPICommonBehavior:
    """Test common behavior across all exchange REST APIs"""

    @pytest.mark.asyncio
    async def test_empty_response_handling(self, mock_ccxt_binance):
        """Test handling of empty API response"""
        mock_ccxt_binance.fetch_ohlcv.return_value = []

        api = BinanceRestAPI()
        candles = await api.fetch_latest_klines(symbol="BTC/USDT", timeframe="1m")

        assert candles == []

    @pytest.mark.asyncio
    async def test_trades_count_always_zero(self, mock_ccxt_binance):
        """Test that trades_count is always 0 for REST API (not provided)"""
        mock_data = create_mock_ohlcv_data(count=1)
        mock_ccxt_binance.fetch_ohlcv.return_value = mock_data

        api = BinanceRestAPI()
        candles = await api.fetch_latest_klines(symbol="BTC/USDT", timeframe="1m")

        assert candles[0].trades_count == 0

    @pytest.mark.asyncio
    async def test_is_synthetic_always_false(self, mock_ccxt_binance):
        """Test that is_synthetic is always False for REST API data"""
        mock_data = create_mock_ohlcv_data(count=1)
        mock_ccxt_binance.fetch_ohlcv.return_value = mock_data

        api = BinanceRestAPI()
        candles = await api.fetch_latest_klines(symbol="BTC/USDT", timeframe="1m")

        assert candles[0].is_synthetic is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
