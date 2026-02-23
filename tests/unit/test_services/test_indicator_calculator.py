"""
Unit tests for IndicatorCalculator

Tests indicator calculation logic with mocked database and persistence layer.
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.models.market_data import Candle
from services.indicator_service.calculator import IndicatorCalculator


def create_test_candle(
    close: float,
    timestamp_offset_minutes: int = 0,
    exchange: str = "binance",
    symbol: str = "BTCUSDT",
    timeframe: str = "1m",
) -> Candle:
    """Helper to create test candles"""
    from datetime import timedelta

    base_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    timestamp = base_time + timedelta(minutes=timestamp_offset_minutes)

    return Candle(
        timestamp=timestamp,
        exchange=exchange,
        symbol=symbol,
        timeframe=timeframe,
        open=Decimal(str(close - 1)),
        high=Decimal(str(close + 1)),
        low=Decimal(str(close - 2)),
        close=Decimal(str(close)),
        volume=Decimal("100.0"),
        quote_volume=Decimal(str(100 * close)),
        trades_count=10,
        is_synthetic=False,
    )


@pytest.fixture
def mock_db():
    """Mock BaseTimeSeriesDB"""
    db = MagicMock()
    db.query_candles = AsyncMock()
    db.insert_indicators = AsyncMock(return_value=1)
    return db


@pytest.fixture
def mock_persistence():
    """Mock IndicatorPersistence"""
    persistence = MagicMock()
    persistence.save_indicators = AsyncMock()
    return persistence


@pytest.fixture
def mock_indicator_loader():
    """Mock IndicatorLoader to return test indicators"""
    with patch("services.indicator_service.calculator.IndicatorLoader") as mock:
        # Create mock indicators
        sma_indicator = MagicMock()
        sma_indicator.get_results.return_value = {"SMA_20": 50000.0, "SMA_50": 49900.0}

        ema_indicator = MagicMock()
        ema_indicator.get_results.return_value = {"EMA_12": 50100.0, "EMA_26": 50050.0}

        rsi_indicator = MagicMock()
        rsi_indicator.get_results.return_value = {"RSI_14": 55.5}

        # Configure loader to return these indicators
        mock.load_from_settings.return_value = {
            "SMA": sma_indicator,
            "EMA": ema_indicator,
            "RSI": rsi_indicator,
        }
        yield mock


@pytest.mark.unit
class TestIndicatorCalculator:
    """Test IndicatorCalculator logic"""

    @pytest.mark.asyncio
    async def test_process_candle_with_sufficient_history(
        self, mock_db, mock_persistence, mock_indicator_loader
    ):
        """Test processing candle with sufficient historical data"""
        calculator = IndicatorCalculator(db=mock_db, persistence=mock_persistence)

        # Create 50 candles (more than minimum of 20)
        candles = [create_test_candle(50000 + i, i) for i in range(50)]
        latest_candle = candles[-1]

        # Process the latest candle
        await calculator.process_candle_with_history(latest_candle, candles)

        # Verify all indicators were calculated
        assert calculator.indicators["SMA"].get_results.called
        assert calculator.indicators["EMA"].get_results.called
        assert calculator.indicators["RSI"].get_results.called

        # Verify persistence was called with combined results
        expected_indicators = {
            "SMA_20": 50000.0,
            "SMA_50": 49900.0,
            "EMA_12": 50100.0,
            "EMA_26": 50050.0,
            "RSI_14": 55.5,
        }

        mock_persistence.save_indicators.assert_called_once_with(
            exchange=latest_candle.exchange,
            symbol=latest_candle.symbol,
            timeframe=latest_candle.timeframe,
            timestamp=latest_candle.timestamp,
            indicators=expected_indicators,
        )

    @pytest.mark.asyncio
    async def test_process_candle_with_insufficient_history(
        self, mock_db, mock_persistence, mock_indicator_loader
    ):
        """Test that processing fails gracefully with insufficient candles"""
        calculator = IndicatorCalculator(db=mock_db, persistence=mock_persistence)

        # Create only 15 candles (less than minimum of 20)
        candles = [create_test_candle(50000 + i, i) for i in range(15)]
        latest_candle = candles[-1]

        # Process should return early without calling persistence
        await calculator.process_candle_with_history(latest_candle, candles)

        # Verify no indicators were calculated
        assert not calculator.indicators["SMA"].get_results.called
        assert not calculator.indicators["EMA"].get_results.called
        assert not calculator.indicators["RSI"].get_results.called

        # Verify persistence was NOT called
        mock_persistence.save_indicators.assert_not_called()

    @pytest.mark.asyncio
    async def test_indicator_calculation_error_handling(
        self, mock_db, mock_persistence, mock_indicator_loader
    ):
        """Test error handling when individual indicator fails"""
        calculator = IndicatorCalculator(db=mock_db, persistence=mock_persistence)

        # Make one indicator fail
        calculator.indicators["SMA"].get_results.side_effect = Exception(
            "SMA calculation failed"
        )

        candles = [create_test_candle(50000 + i, i) for i in range(50)]
        latest_candle = candles[-1]

        # Should continue and calculate other indicators
        await calculator.process_candle_with_history(latest_candle, candles)

        # Verify other indicators still calculated
        assert calculator.indicators["EMA"].get_results.called
        assert calculator.indicators["RSI"].get_results.called

        # Verify persistence called with partial results (no SMA)
        call_args = mock_persistence.save_indicators.call_args
        indicators_saved = call_args.kwargs["indicators"]

        assert "EMA_12" in indicators_saved
        assert "RSI_14" in indicators_saved
        assert "SMA_20" not in indicators_saved  # Failed indicator excluded

    @pytest.mark.asyncio
    async def test_no_results_from_any_indicator(
        self, mock_db, mock_persistence, mock_indicator_loader
    ):
        """Test behavior when no indicators return results"""
        calculator = IndicatorCalculator(db=mock_db, persistence=mock_persistence)

        # Make all indicators return empty results
        calculator.indicators["SMA"].get_results.return_value = {}
        calculator.indicators["EMA"].get_results.return_value = {}
        calculator.indicators["RSI"].get_results.return_value = {}

        candles = [create_test_candle(50000 + i, i) for i in range(50)]
        latest_candle = candles[-1]

        await calculator.process_candle_with_history(latest_candle, candles)

        # Verify persistence NOT called when no results
        mock_persistence.save_indicators.assert_not_called()

    @pytest.mark.asyncio
    async def test_indicator_loader_called_during_init(
        self, mock_db, mock_persistence, mock_indicator_loader
    ):
        """Test that IndicatorLoader is called during initialization"""
        calculator = IndicatorCalculator(db=mock_db, persistence=mock_persistence)

        # Verify loader was called
        mock_indicator_loader.load_from_settings.assert_called_once()

        # Verify indicators loaded
        assert len(calculator.indicators) == 3
        assert "SMA" in calculator.indicators
        assert "EMA" in calculator.indicators
        assert "RSI" in calculator.indicators

    @pytest.mark.asyncio
    async def test_process_with_exact_minimum_candles(
        self, mock_db, mock_persistence, mock_indicator_loader
    ):
        """Test processing with exactly 20 candles (minimum)"""
        calculator = IndicatorCalculator(db=mock_db, persistence=mock_persistence)

        # Create exactly 20 candles
        candles = [create_test_candle(50000 + i, i) for i in range(20)]
        latest_candle = candles[-1]

        await calculator.process_candle_with_history(latest_candle, candles)

        # Should process successfully
        mock_persistence.save_indicators.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_with_different_symbols(
        self, mock_db, mock_persistence, mock_indicator_loader
    ):
        """Test processing candles for different symbols"""
        calculator = IndicatorCalculator(db=mock_db, persistence=mock_persistence)

        # Process BTC
        btc_candles = [
            create_test_candle(50000 + i, i, symbol="BTCUSDT") for i in range(50)
        ]
        await calculator.process_candle_with_history(btc_candles[-1], btc_candles)

        # Process ETH
        eth_candles = [
            create_test_candle(3000 + i, i, symbol="ETHUSDT") for i in range(50)
        ]
        await calculator.process_candle_with_history(eth_candles[-1], eth_candles)

        # Verify both were processed
        assert mock_persistence.save_indicators.call_count == 2

        # Verify correct symbols
        first_call = mock_persistence.save_indicators.call_args_list[0]
        assert first_call.kwargs["symbol"] == "BTCUSDT"

        second_call = mock_persistence.save_indicators.call_args_list[1]
        assert second_call.kwargs["symbol"] == "ETHUSDT"

    @pytest.mark.asyncio
    async def test_process_with_different_exchanges(
        self, mock_db, mock_persistence, mock_indicator_loader
    ):
        """Test processing candles from different exchanges"""
        calculator = IndicatorCalculator(db=mock_db, persistence=mock_persistence)

        # Process Binance
        binance_candles = [
            create_test_candle(50000 + i, i, exchange="binance") for i in range(50)
        ]
        await calculator.process_candle_with_history(binance_candles[-1], binance_candles)

        # Process Coinbase
        coinbase_candles = [
            create_test_candle(50000 + i, i, exchange="coinbase") for i in range(50)
        ]
        await calculator.process_candle_with_history(
            coinbase_candles[-1], coinbase_candles
        )

        # Verify both exchanges processed
        assert mock_persistence.save_indicators.call_count == 2

        first_call = mock_persistence.save_indicators.call_args_list[0]
        assert first_call.kwargs["exchange"] == "binance"

        second_call = mock_persistence.save_indicators.call_args_list[1]
        assert second_call.kwargs["exchange"] == "coinbase"

    @pytest.mark.asyncio
    async def test_process_with_different_timeframes(
        self, mock_db, mock_persistence, mock_indicator_loader
    ):
        """Test processing candles with different timeframes"""
        calculator = IndicatorCalculator(db=mock_db, persistence=mock_persistence)

        # Process 1m candles
        candles_1m = [
            create_test_candle(50000 + i, i, timeframe="1m") for i in range(50)
        ]
        await calculator.process_candle_with_history(candles_1m[-1], candles_1m)

        # Process 5m candles
        candles_5m = [
            create_test_candle(50000 + i, i * 5, timeframe="5m") for i in range(50)
        ]
        await calculator.process_candle_with_history(candles_5m[-1], candles_5m)

        # Verify both timeframes processed
        assert mock_persistence.save_indicators.call_count == 2

        first_call = mock_persistence.save_indicators.call_args_list[0]
        assert first_call.kwargs["timeframe"] == "1m"

        second_call = mock_persistence.save_indicators.call_args_list[1]
        assert second_call.kwargs["timeframe"] == "5m"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
