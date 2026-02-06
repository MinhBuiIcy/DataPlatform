"""
Unit tests for moving average indicators

Tests with hand-calculated and textbook examples to verify correctness
"""

from decimal import Decimal

import pytest

from core.models.market_data import Candle
from domain.indicators.moving_averages import EMA, SMA, WMA


def create_test_candle(close: float, timestamp_offset: int = 0) -> Candle:
    """Helper to create test candle with minimal fields"""
    from datetime import datetime, timedelta, timezone

    return Candle(
        timestamp=datetime.now(timezone.utc) + timedelta(minutes=timestamp_offset),
        exchange="binance",
        symbol="BTCUSDT",
        timeframe="1m",
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=Decimal(100),
        quote_volume=Decimal(100 * close),
        trades_count=10,
        is_synthetic=False,
    )


class TestSMA:
    """Test Simple Moving Average with known values"""

    def test_sma_hand_calculated(self):
        """Test SMA with hand-calculated values"""
        # Dataset: prices increasing
        prices = [100, 102, 101, 103, 105, 107, 106, 108, 110, 109]
        candles = [create_test_candle(p, i) for i, p in enumerate(prices)]

        # SMA(3) = average of last 3 prices
        sma = SMA(period=3)
        result = sma.calculate(candles)

        # Hand calculation: (110 + 109 + 108) / 3 = 109.0
        expected = 109.0

        assert result is not None
        assert abs(result - expected) < 0.01, f"SMA mismatch: {result} vs {expected}"

    def test_sma_known_dataset(self):
        """Test SMA against known financial dataset"""
        # From technical analysis textbook
        prices = [
            44.34,
            44.09,
            44.15,
            43.61,
            44.33,
            44.83,
            45.10,
            45.42,
            45.84,
            46.08,
            45.89,
            46.03,
            45.61,
            46.28,
            46.28,
            46.00,
            46.03,
            46.41,
            46.22,
            45.64,
        ]

        candles = [create_test_candle(p, i) for i, p in enumerate(prices)]

        sma = SMA(period=10)
        result = sma.calculate(candles)

        # Hand-calculated SMA(10) for last 10 prices
        last_10 = prices[-10:]
        expected = sum(last_10) / 10  # 45.97

        assert result is not None
        assert abs(result - expected) < 0.01

    def test_sma_insufficient_data(self):
        """Test SMA raises error with insufficient candles"""
        prices = [100, 102, 104]  # Only 3 candles
        candles = [create_test_candle(p, i) for i, p in enumerate(prices)]

        sma = SMA(period=10)

        with pytest.raises(ValueError, match="Need 10 candles, got 3"):
            sma.calculate(candles)


class TestEMA:
    """Test Exponential Moving Average with known values"""

    def test_ema_textbook_example(self):
        """Test EMA against Investopedia textbook example"""
        # From Investopedia EMA calculation example
        prices = [
            22.27,
            22.19,
            22.08,
            22.17,
            22.18,
            22.13,
            22.23,
            22.43,
            22.24,
            22.29,
            22.15,
            22.39,
            22.38,
            22.61,
            23.36,
        ]

        candles = [create_test_candle(p, i) for i, p in enumerate(prices)]

        ema = EMA(period=10)
        result = ema.calculate(candles)

        # Expected EMA(10) from textbook (approximate)
        expected = 22.47

        assert result is not None
        assert abs(result - expected) < 0.1  # Allow small variance due to rounding

    def test_ema_vs_sma_convergence(self):
        """Test EMA converges to SMA with stable prices"""
        # Stable prices (no change)
        prices = [100.0] * 50  # 50 candles at same price

        candles = [create_test_candle(p, i) for i, p in enumerate(prices)]

        ema = EMA(period=20)
        sma = SMA(period=20)

        ema_result = ema.calculate(candles)
        sma_result = sma.calculate(candles)

        # With stable prices, EMA should equal SMA
        assert abs(ema_result - sma_result) < 0.01


class TestWMA:
    """Test Weighted Moving Average"""

    def test_wma_basic_calculation(self):
        """Test WMA gives more weight to recent prices"""
        # Prices: older values low, recent values high
        prices = [100, 100, 100, 110, 110]
        candles = [create_test_candle(p, i) for i, p in enumerate(prices)]

        wma = WMA(period=5)
        sma = SMA(period=5)

        wma_result = wma.calculate(candles)
        sma_result = sma.calculate(candles)

        # WMA should be higher than SMA (more weight on recent high prices)
        assert wma_result > sma_result
