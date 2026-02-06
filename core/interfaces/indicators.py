"""
Abstract interface for technical indicators

Cloud-agnostic indicator base class
"""

from abc import ABC, abstractmethod
from typing import Optional

from core.models.market_data import Candle


class BaseIndicator(ABC):
    """
    Cloud-agnostic indicator interface

    Design principle:
    - Pure calculation logic (no database dependency)
    - Testable with mock data
    - Reusable across phases (trading, backtesting, ML)

    Implementations:
    - SMA, EMA, WMA (domain/indicators/moving_averages.py)
    - RSI, MACD, Stochastic (domain/indicators/momentum.py)
    """

    def __init__(self, period: int, **kwargs):
        """
        Initialize indicator

        Args:
            period: Look-back period for calculation
            **kwargs: Additional indicator-specific parameters
        """
        self.period = period
        self.name = self.__class__.__name__
        self.params = {"period": period, **kwargs}

    @abstractmethod
    def calculate(self, candles: list[Candle]) -> Optional[float]:
        """
        Calculate indicator from candle data

        Args:
            candles: List of CLOSED candles, ordered by time DESC
                     (newest first). Must contain at least self.period candles.

        Returns:
            Indicator value (float) or None if insufficient data

        Raises:
            ValueError: If candles list is invalid

        Note:
            Implementation should:
            1. Call validate_input() first
            2. Extract price data (close, high, low, volume)
            3. Use TA-Lib for calculation (industry standard)
            4. Return the most recent value
        """

    def get_results(self, candles: list[Candle]) -> dict[str, float]:
        """
        Get indicator results as dict (for polymorphic calculation)

        Default implementation returns single value: {self.name: value}
        Override for multi-value indicators (e.g., MACD returns macd, signal, histogram)

        Args:
            candles: List of candles

        Returns:
            Dict of results: {"SMA_20": 45000.5} or {"MACD": ..., "MACD_signal": ...}
            Empty dict if calculation fails

        Example:
            >>> sma = SMA(period=20)
            >>> sma.get_results(candles)
            {"SMA": 45123.45}

            >>> macd = MACD()
            >>> macd.get_results(candles)
            {"MACD": 123.45, "MACD_signal": 100.0, "MACD_histogram": 23.45}
        """
        value = self.calculate(candles)
        if value is None:
            return {}
        return {self.name: value}

    def validate_input(self, candles: list[Candle]) -> None:
        """
        Validate input candles

        Args:
            candles: List of candles to validate

        Raises:
            ValueError: If candles list is invalid
        """
        if not candles:
            raise ValueError(f"{self.name}: Empty candles list")

        if len(candles) < self.period:
            raise ValueError(
                f"{self.name}: Need {self.period} candles, got {len(candles)}"
            )

    def __repr__(self) -> str:
        """String representation"""
        params_str = ", ".join(f"{k}={v}" for k, v in self.params.items())
        return f"{self.name}({params_str})"
