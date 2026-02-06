"""
Indicator Loader - Load indicators from config

Responsibility: Bridge between config layer and domain layer
- Load indicator configs from settings (config layer)
- Use IndicatorRegistry to create instances (domain layer)
- Return ready-to-use indicator instances

This is SERVICE layer - knows about config, uses domain factories
"""

import logging

from config.settings import get_settings
from core.interfaces.indicators import BaseIndicator
from domain.indicators.registry import IndicatorRegistry

logger = logging.getLogger(__name__)


class IndicatorLoader:
    """Load indicators from YAML config using registry"""

    @staticmethod
    def load_from_settings() -> dict[str, BaseIndicator]:
        """
        Load indicators from settings.INDICATORS

        Returns:
            Dict of indicator instances: {"SMA_20": SMA(20), "EMA_12": EMA(12), ...}

        Example:
            >>> indicators = IndicatorLoader.load_from_settings()
            >>> print(indicators.keys())
            dict_keys(['SMA_20', 'SMA_50', 'EMA_12', 'RSI_14', 'MACD'])

            >>> indicators["SMA_20"].calculate(candles)
            45123.45
        """
        settings = get_settings()
        indicators = {}

        for config in settings.INDICATORS:
            name = config["name"]
            indicator_type = config["type"]
            params = config.get("params", {})

            try:
                # Use domain registry to create indicator
                indicator = IndicatorRegistry.create(indicator_type, **params)
                indicators[name] = indicator
                logger.debug(f"  ✓ Loaded {name}: {indicator}")

            except ValueError as e:
                logger.warning(f"  ✗ Skipping {name}: {e}")
            except Exception as e:
                logger.error(f"  ✗ Failed to load {name}: {e}")

        logger.info(f"✓ Loaded {len(indicators)} indicators: {list(indicators.keys())}")
        return indicators
