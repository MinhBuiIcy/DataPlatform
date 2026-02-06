"""
Indicator Service - Technical Indicator Calculation

Event-driven service that:
1. Consumes candle events from Kafka
2. Calculates technical indicators (SMA, EMA, RSI, MACD)
3. Handles gap-filling for missing candles
4. Persists to ClickHouse + caches in Redis
"""

from services.indicator_service.calculator import IndicatorCalculator
from services.indicator_service.persistence import IndicatorPersistence

__all__ = ["IndicatorCalculator", "IndicatorPersistence"]
