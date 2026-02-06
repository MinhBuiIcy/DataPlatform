"""
Momentum indicators

Implementations:
- RSI: Relative Strength Index
- MACD: Moving Average Convergence Divergence
- Stochastic: Stochastic Oscillator
"""

from typing import Optional

import numpy as np
import talib

from core.interfaces.indicators import BaseIndicator
from core.models.market_data import Candle


class RSI(BaseIndicator):
    """
    Relative Strength Index

    Formula:
        RS = Average Gain / Average Loss (over N periods)
        RSI = 100 - (100 / (1 + RS))

    Interpretation:
        - RSI > 70: Overbought
        - RSI < 30: Oversold
        - RSI = 50: Neutral

    Example:
        >>> candles = [...]  # 100 candles
        >>> rsi = RSI(period=14)
        >>> value = rsi.calculate(candles)
        >>> if value > 70:
        ...     print("Overbought")
    """

    def __init__(self, period: int = 14):
        """
        Initialize RSI

        Args:
            period: Look-back period (default: 14)
        """
        super().__init__(period=period)

    def calculate(self, candles: list[Candle]) -> Optional[float]:
        """Calculate RSI"""
        self.validate_input(candles)

        closes = np.array([float(c.close) for c in candles])
        rsi_values = talib.RSI(closes, timeperiod=self.period)

        return float(rsi_values[-1]) if not np.isnan(rsi_values[-1]) else None


class MACD(BaseIndicator):
    """
    Moving Average Convergence Divergence

    Components:
        - MACD Line = EMA(12) - EMA(26)
        - Signal Line = EMA(9) of MACD Line
        - Histogram = MACD Line - Signal Line

    Interpretation:
        - MACD crosses above Signal: Bullish
        - MACD crosses below Signal: Bearish
        - Histogram > 0: Upward momentum
        - Histogram < 0: Downward momentum

    Example:
        >>> candles = [...]  # 200 candles
        >>> macd = MACD()
        >>> result = macd.calculate_full(candles)
        >>> if result['macd'] > result['signal']:
        ...     print("Bullish")
    """

    def __init__(
        self, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9
    ):
        """
        Initialize MACD

        Args:
            fast_period: Fast EMA period (default: 12)
            slow_period: Slow EMA period (default: 26)
            signal_period: Signal line EMA period (default: 9)
        """
        # Use slow_period as the main period for validation
        super().__init__(
            period=slow_period, fast=fast_period, signal=signal_period
        )
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period

    def calculate(self, candles: list[Candle]) -> Optional[float]:
        """
        Calculate MACD histogram value

        Returns:
            MACD histogram (MACD line - Signal line)
        """
        result = self.calculate_full(candles)
        return result["histogram"] if result else None

    def calculate_full(self, candles: list[Candle]) -> Optional[dict]:
        """
        Calculate all MACD components

        Returns:
            Dict with keys: macd, signal, histogram
            Or None if insufficient data
        """
        self.validate_input(candles)

        closes = np.array([float(c.close) for c in candles])
        macd, signal, histogram = talib.MACD(
            closes,
            fastperiod=self.fast_period,
            slowperiod=self.slow_period,
            signalperiod=self.signal_period,
        )

        if np.isnan(macd[-1]) or np.isnan(signal[-1]) or np.isnan(histogram[-1]):
            return None

        return {
            "macd": float(macd[-1]),
            "signal": float(signal[-1]),
            "histogram": float(histogram[-1]),
        }

    def get_results(self, candles: list[Candle]) -> dict[str, float]:
        """
        Override to return all MACD components

        Returns:
            Dict with MACD, MACD_signal, MACD_histogram
        """
        result = self.calculate_full(candles)
        if not result:
            return {}

        return {
            "MACD": result["macd"],
            "MACD_signal": result["signal"],
            "MACD_histogram": result["histogram"],
        }


class Stochastic(BaseIndicator):
    """
    Stochastic Oscillator

    Formula:
        %K = (Close - Low14) / (High14 - Low14) × 100
        %D = SMA(3) of %K

    Interpretation:
        - %K > 80: Overbought
        - %K < 20: Oversold
        - %K crosses above %D: Bullish
        - %K crosses below %D: Bearish

    Example:
        >>> candles = [...]  # 50 candles
        >>> stoch = Stochastic()
        >>> result = stoch.calculate_full(candles)
        >>> if result['k'] > 80:
        ...     print("Overbought")
    """

    def __init__(
        self,
        k_period: int = 14,
        k_slow_period: int = 3,
        d_period: int = 3,
    ):
        """
        Initialize Stochastic

        Args:
            k_period: %K period (default: 14)
            k_slow_period: %K slowing period (default: 3)
            d_period: %D period (default: 3)
        """
        super().__init__(
            period=k_period,
            k_slow=k_slow_period,
            d=d_period,
        )
        self.k_period = k_period
        self.k_slow_period = k_slow_period
        self.d_period = d_period

    def calculate(self, candles: list[Candle]) -> Optional[float]:
        """
        Calculate Stochastic %K value

        Returns:
            %K value (0-100)
        """
        result = self.calculate_full(candles)
        return result["k"] if result else None

    def calculate_full(self, candles: list[Candle]) -> Optional[dict]:
        """
        Calculate both %K and %D values

        Returns:
            Dict with keys: k, d
            Or None if insufficient data
        """
        self.validate_input(candles)

        highs = np.array([float(c.high) for c in candles])
        lows = np.array([float(c.low) for c in candles])
        closes = np.array([float(c.close) for c in candles])

        k, d = talib.STOCH(
            highs,
            lows,
            closes,
            fastk_period=self.k_period,
            slowk_period=self.k_slow_period,
            slowd_period=self.d_period,
        )

        if np.isnan(k[-1]) or np.isnan(d[-1]):
            return None

        return {
            "k": float(k[-1]),
            "d": float(d[-1]),
        }

    def get_results(self, candles: list[Candle]) -> dict[str, float]:
        """
        Override to return both %K and %D

        Returns:
            Dict with Stochastic_K and Stochastic_D
        """
        result = self.calculate_full(candles)
        if not result:
            return {}

        return {
            "Stochastic_K": result["k"],
            "Stochastic_D": result["d"],
        }
