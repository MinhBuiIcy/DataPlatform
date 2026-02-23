"""
Indicator registry for managing and creating indicators

Factory pattern for indicator creation
"""

from core.interfaces.indicators import BaseIndicator
from domain.indicators.momentum import MACD, RSI, Stochastic
from domain.indicators.moving_averages import EMA, SMA, WMA


class IndicatorRegistry:
    """
    Registry for indicator creation

    Provides factory methods for creating indicators
    """

    # Registry of available indicators
    _indicators: dict[str, type[BaseIndicator]] = {
        "sma": SMA,
        "ema": EMA,
        "wma": WMA,
        "rsi": RSI,
        "macd": MACD,
        "stochastic": Stochastic,
    }

    @classmethod
    def create(cls, indicator_type: str, **params) -> BaseIndicator:
        """
        Create indicator by type

        Args:
            indicator_type: Indicator type (sma, ema, rsi, macd, etc.)
            **params: Indicator parameters (including optional 'name' for custom naming)

        Returns:
            Indicator instance

        Raises:
            ValueError: If indicator type is not found

        Example:
            >>> registry = IndicatorRegistry()
            >>> sma = registry.create("sma", period=20, name="SMA_20")
            >>> rsi = registry.create("rsi", period=14, name="RSI_14")
            >>> macd = registry.create("macd", fast_period=12, slow_period=26, name="MACD")
        """
        indicator_class = cls._indicators.get(indicator_type.lower())
        if not indicator_class:
            available = ", ".join(cls._indicators.keys())
            raise ValueError(f"Unknown indicator: {indicator_type}. Available: {available}")

        return indicator_class(**params)

    @classmethod
    def register(cls, name: str, indicator_class: type[BaseIndicator]) -> None:
        """
        Register a new indicator

        Args:
            name: Indicator name
            indicator_class: Indicator class (must inherit from BaseIndicator)

        Example:
            >>> class MyIndicator(BaseIndicator):
            ...     def calculate(self, candles):
            ...         return 42.0
            >>> IndicatorRegistry.register("my_indicator", MyIndicator)
        """
        cls._indicators[name.lower()] = indicator_class

    @classmethod
    def list_indicators(cls) -> list[str]:
        """
        List all available indicators

        Returns:
            List of indicator names

        Example:
            >>> IndicatorRegistry.list_indicators()
            ['sma', 'ema', 'wma', 'rsi', 'macd', 'stochastic']
        """
        return sorted(cls._indicators.keys())
