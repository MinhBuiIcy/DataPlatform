"""
Moving average indicators

Implementations:
- SMA: Simple Moving Average
- EMA: Exponential Moving Average
- WMA: Weighted Moving Average
"""

import logging

import numpy as np
import talib

from core.interfaces.indicators import BaseIndicator
from core.models.market_data import Candle

logger = logging.getLogger(__name__)


class SMA(BaseIndicator):
    """
    Simple Moving Average

    Formula: SMA = SUM(Close) / N

    Example:
        >>> candles = [...]  # 50 candles
        >>> sma = SMA(period=20)
        >>> value = sma.calculate(candles)
    """

    def __init__(self, period: int, name: str = None):
        """
        Initialize SMA

        Args:
            period: Look-back period
            name: Custom name for this indicator (e.g., "SMA_20"). If None, uses class name.
        """
        super().__init__(period=period, name=name)

    def calculate(self, candles: list[Candle]) -> float | None:
        """Calculate SMA"""
        self.validate_input(candles)

        # Extract closing prices (convert Decimal to float)
        closes = np.array([float(c.close) for c in candles])

        # TA-Lib SMA
        sma_values = talib.SMA(closes, timeperiod=self.period)

        # Return most recent non-NaN value
        return float(sma_values[-1]) if not np.isnan(sma_values[-1]) else None


class EMA(BaseIndicator):
    """
    Exponential Moving Average

    Formula: EMA = α × Price + (1-α) × EMA_prev
    where α = 2 / (period + 1)

    Note:
        EMA requires warm-up period. For accurate results,
        load 4× the period (e.g., 200 candles for EMA(50))

    Example:
        >>> candles = [...]  # 200 candles for EMA(50)
        >>> ema = EMA(period=50)
        >>> value = ema.calculate(candles)
    """

    def __init__(self, period: int, name: str = None):
        """
        Initialize EMA

        Args:
            period: Look-back period
            name: Custom name for this indicator (e.g., "EMA_12"). If None, uses class name.
        """
        super().__init__(period=period, name=name)

    def calculate(self, candles: list[Candle]) -> float | None:
        """Calculate EMA"""
        self.validate_input(candles)

        # Warn if insufficient warm-up data
        if len(candles) < self.period * 4:
            logger.warning(
                f"EMA({self.period}): Only {len(candles)} candles, "
                f"recommend {self.period * 4} for convergence"
            )

        closes = np.array([float(c.close) for c in candles])
        ema_values = talib.EMA(closes, timeperiod=self.period)

        return float(ema_values[-1]) if not np.isnan(ema_values[-1]) else None


class WMA(BaseIndicator):
    """
    Weighted Moving Average

    Formula: WMA = SUM(Price × Weight) / SUM(Weight)
    where Weight = N, N-1, N-2, ..., 1

    Example:
        >>> candles = [...]  # 30 candles
        >>> wma = WMA(period=20)
        >>> value = wma.calculate(candles)
    """

    def calculate(self, candles: list[Candle]) -> float | None:
        """Calculate WMA"""
        self.validate_input(candles)

        closes = np.array([float(c.close) for c in candles])
        wma_values = talib.WMA(closes, timeperiod=self.period)

        return float(wma_values[-1]) if not np.isnan(wma_values[-1]) else None
