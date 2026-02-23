"""
Indicator Calculator - Simplified for Phase 2

No gap handling, no complex logic.
Just calculate indicators from candles and persist.
"""

import logging

from config.settings import get_settings
from core.interfaces.database import BaseTimeSeriesDB
from core.models.market_data import Candle
from services.indicator_service.indicator_loader import IndicatorLoader
from services.indicator_service.persistence import IndicatorPersistence

logger = logging.getLogger(__name__)


class IndicatorCalculator:
    """Calculate technical indicators from candles (simplified)"""

    def __init__(self, db: BaseTimeSeriesDB, persistence: IndicatorPersistence):
        self.db = db
        self.persistence = persistence
        self.settings = get_settings()

        # Load indicators from config
        self.indicators = IndicatorLoader.load_from_settings()
        logger.info(f"Loaded {len(self.indicators)} indicators")

    async def process_candle_with_history(self, candle: Candle, candles: list[Candle]) -> None:
        """
        Process a single candle with pre-fetched historical data.

        Args:
            candle: Latest candle to process
            candles: Historical candles (including latest) for indicator calculation
        """
        try:
            # Need minimum candles for calculation
            if len(candles) < 20:
                logger.debug(
                    f"Insufficient candles ({len(candles)}) for "
                    f"{candle.exchange}/{candle.symbol}/{candle.timeframe}"
                )
                return

            # Calculate all indicators
            results = {}
            for name, indicator in self.indicators.items():
                try:
                    # Each indicator returns dict: {"SMA_20": 50000.5, ...}
                    indicator_results = indicator.get_results(candles)
                    results.update(indicator_results)
                except ValueError as e:
                    # Expected for symbols with insufficient candles (low volume)
                    logger.debug(f"Skipping {name}: {e}")
                except Exception as e:
                    # Unexpected errors should still be logged as ERROR
                    logger.error(f"Error calculating {name}: {e}")

            if not results:
                return

            # Save to ClickHouse + Redis
            await self.persistence.save_indicators(
                exchange=candle.exchange,
                symbol=candle.symbol,
                timeframe=candle.timeframe,
                timestamp=candle.timestamp,
                indicators=results,
            )

            logger.debug(
                f"✅ {len(results)} indicators for "
                f"{candle.exchange}/{candle.symbol}/{candle.timeframe}"
            )

        except Exception as e:
            logger.error(f"Error processing candle {candle.exchange}/{candle.symbol}: {e}")
