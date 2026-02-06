"""
Unit tests for momentum indicators (RSI, MACD, Stochastic)

Tests with known scenarios: overbought, oversold, neutral
"""

import pytest

from core.models.market_data import Candle
from domain.indicators.momentum import MACD, RSI, Stochastic
from tests.unit.indicators.test_moving_averages import create_test_candle


class TestRSI:
    """Test Relative Strength Index with known scenarios"""

    def test_rsi_neutral(self):
        """Test RSI ≈ 50 with sideways market (neutral)"""
        # Sideways market with small oscillations
        prices = [100 + (i % 2) * 0.5 for i in range(30)]  # Oscillate slightly

        candles = [create_test_candle(p, i) for i, p in enumerate(prices)]

        rsi = RSI(period=14)
        result = rsi.calculate(candles)

        # RSI should be neutral (around 50)
        assert result is not None
        assert 40 <= result <= 60, f"RSI should be neutral: {result}"

    def test_rsi_overbought(self):
        """Test RSI > 70 with strong uptrend (overbought)"""
        # Prices trending up strongly
        prices = [50 + i * 0.5 for i in range(30)]  # Steady increase
        candles = [create_test_candle(p, i) for i, p in enumerate(prices)]

        rsi = RSI(period=14)
        result = rsi.calculate(candles)

        # Should be overbought (>70)
        assert result is not None
        assert result > 70, f"RSI should be overbought: {result}"
        assert result <= 100, "RSI cannot exceed 100"

    def test_rsi_oversold(self):
        """Test RSI < 30 with strong downtrend (oversold)"""
        # Prices trending down strongly
        prices = [100 - i * 0.5 for i in range(30)]  # Steady decrease
        candles = [create_test_candle(p, i) for i, p in enumerate(prices)]

        rsi = RSI(period=14)
        result = rsi.calculate(candles)

        # Should be oversold (<30)
        assert result is not None
        assert result < 30, f"RSI should be oversold: {result}"
        assert result >= 0, "RSI cannot be negative"

    def test_rsi_bounds(self):
        """Test RSI always stays within 0-100 bounds"""
        # Extreme volatility
        prices = [100, 110, 95, 115, 90, 120, 85, 125, 80, 130] * 3
        candles = [create_test_candle(p, i) for i, p in enumerate(prices)]

        rsi = RSI(period=14)
        result = rsi.calculate(candles)

        assert result is not None
        assert 0 <= result <= 100, f"RSI out of bounds: {result}"


class TestMACD:
    """Test MACD (Moving Average Convergence Divergence)"""

    def test_macd_components(self):
        """Test MACD returns all components: macd, signal, histogram"""
        # Trending prices
        prices = [100 + i * 0.3 for i in range(50)]
        candles = [create_test_candle(p, i) for i, p in enumerate(prices)]

        macd = MACD(fast_period=12, slow_period=26, signal_period=9)
        result = macd.calculate_full(candles)

        assert result is not None
        assert "macd" in result
        assert "signal" in result
        assert "histogram" in result

    def test_macd_histogram_calculation(self):
        """Test histogram = MACD line - Signal line"""
        prices = [100 + i * 0.2 for i in range(50)]
        candles = [create_test_candle(p, i) for i, p in enumerate(prices)]

        macd = MACD()
        result = macd.calculate_full(candles)

        assert result is not None

        # Verify histogram calculation
        expected_histogram = result["macd"] - result["signal"]
        assert abs(result["histogram"] - expected_histogram) < 0.0001

    def test_macd_bullish_signal(self):
        """Test MACD > Signal indicates bullish momentum"""
        # Accelerating uptrend (exponential growth) for clear bullish signal
        prices = [100 * (1.02 ** i) for i in range(50)]  # 2% growth per period
        candles = [create_test_candle(p, i) for i, p in enumerate(prices)]

        macd = MACD()
        result = macd.calculate_full(candles)

        assert result is not None
        # In accelerating uptrend, MACD should be above signal
        assert result["macd"] > result["signal"], f"MACD ({result['macd']:.2f}) should be > signal ({result['signal']:.2f})"
        assert result["histogram"] > 0, "Histogram should be positive"

    def test_macd_get_results_polymorphism(self):
        """Test get_results() returns all three values"""
        prices = [100 + i * 0.5 for i in range(50)]
        candles = [create_test_candle(p, i) for i, p in enumerate(prices)]

        macd = MACD()
        results = macd.get_results(candles)

        # Should return dict with 3 keys
        assert len(results) == 3
        assert "MACD" in results
        assert "MACD_signal" in results
        assert "MACD_histogram" in results


class TestStochastic:
    """Test Stochastic Oscillator"""

    def test_stochastic_overbought(self):
        """Test Stochastic > 80 in strong uptrend"""
        # Prices at recent highs
        prices = [100 + i * 2 for i in range(30)]
        candles = [create_test_candle(p, i) for i, p in enumerate(prices)]

        stoch = Stochastic(k_period=14, k_slow_period=3, d_period=3)
        result = stoch.calculate_full(candles)

        assert result is not None
        assert result["k"] > 80, "Stochastic should be overbought"
        assert result["k"] <= 100

    def test_stochastic_oversold(self):
        """Test Stochastic < 20 in strong downtrend"""
        # Prices at recent lows
        prices = [100 - i * 2 for i in range(30)]
        candles = [create_test_candle(p, i) for i, p in enumerate(prices)]

        stoch = Stochastic()
        result = stoch.calculate_full(candles)

        assert result is not None
        assert result["k"] < 20, "Stochastic should be oversold"
        assert result["k"] >= 0

    def test_stochastic_bounds(self):
        """Test Stochastic always stays within 0-100 bounds"""
        # Volatile prices
        prices = [100, 120, 90, 130, 85, 135, 80, 140] * 3
        candles = [create_test_candle(p, i) for i, p in enumerate(prices)]

        stoch = Stochastic()
        result = stoch.calculate_full(candles)

        assert result is not None
        assert 0 <= result["k"] <= 100
        assert 0 <= result["d"] <= 100
