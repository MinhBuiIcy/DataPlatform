"""
Technical indicators module

Exports:
- BaseIndicator (core/interfaces/indicators.py)
- Moving averages: SMA, EMA, WMA
- Momentum: RSI, MACD, Stochastic
- Registry: IndicatorRegistry
"""

from core.interfaces.indicators import BaseIndicator
from domain.indicators.momentum import MACD, RSI, Stochastic
from domain.indicators.moving_averages import EMA, SMA, WMA
from domain.indicators.registry import IndicatorRegistry

__all__ = [
    "BaseIndicator",
    "SMA",
    "EMA",
    "WMA",
    "RSI",
    "MACD",
    "Stochastic",
    "IndicatorRegistry",
]
