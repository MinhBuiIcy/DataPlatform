"""
Indicator Calculator - Core calculation logic

Clean separation of concerns:
- Query candles from DB
- Process gaps (via GapHandler)
- Calculate indicators (via loaded indicators)
- Persist results (via IndicatorPersistence)

Architecture:
    IndicatorLoader → Load indicators from config
    GapHandler → Detect and fill gaps
    IndicatorCalculator → Orchestrate calculation flow
    IndicatorPersistence → Save to ClickHouse/Redis
"""

import logging

from config.settings import get_settings
from core.interfaces.database import BaseTimeSeriesDB
from services.indicator_service.gap_handler import GapHandler
from services.indicator_service.indicator_loader import IndicatorLoader
from services.indicator_service.persistence import IndicatorPersistence

logger = logging.getLogger(__name__)


class IndicatorCalculator:
    """Calculate technical indicators from candle events"""

    def __init__(self, db: BaseTimeSeriesDB, persistence: IndicatorPersistence):
        self.db = db
        self.persistence = persistence
        self.settings = get_settings()

        # Load components
        self.indicators = IndicatorLoader.load_from_settings()
        self.gap_handler = GapHandler()

    async def process_candle_event(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
    ) -> None:
        """
        Process candle event - main entry point

        Steps:
        1. Query historical candles
        2. Process gaps (detect + fill)
        3. Validate data sufficiency
        4. Calculate indicators
        5. Persist results

        Args:
            exchange: Exchange name (binance, coinbase, etc.)
            symbol: Trading pair (BTCUSDT, BTC-USD, etc.)
            timeframe: Candle interval (1m, 5m, 1h, etc.)
        """
        try:
            # Step 1: Query candles
            candles = await self._query_candles(exchange, symbol, timeframe)
            if not candles:
                logger.warning(f"No candles found for {exchange}/{symbol}/{timeframe}")
                return

            # Step 2: Process gaps
            candles = self.gap_handler.process_candles(candles, timeframe, exchange, symbol)
            if not candles:
                return  # Skip calculation (gap filling disabled or ratio too high)

            # Step 3: Validate data sufficiency
            if not self._validate_data_sufficiency(candles, exchange, symbol, timeframe):
                return

            # Step 4: Calculate all indicators
            results = self._calculate_indicators(candles)
            if not results:
                logger.warning(f"No indicators calculated for {exchange}/{symbol}/{timeframe}")
                return

            # Step 5: Persist results
            await self.persistence.save_indicators(
                exchange=exchange,
                symbol=symbol,
                timeframe=timeframe,
                timestamp=candles[-1].timestamp,
                indicators=results,
            )

            logger.info(
                f"✅ Calculated {len(results)} indicators for {exchange}/{symbol}/{timeframe}"
            )

        except Exception as e:
            logger.error(
                f"❌ Error processing {exchange}/{symbol}/{timeframe}: {e}",
                exc_info=True,
            )

    async def _query_candles(self, exchange: str, symbol: str, timeframe: str) -> list:
        """Query historical candles from database"""
        return await self.db.query_candles(
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
            limit=self.settings.INDICATOR_CANDLE_LOOKBACK,
        )

    def _validate_data_sufficiency(
        self,
        candles: list,
        exchange: str,
        symbol: str,
        timeframe: str,
    ) -> bool:
        """
        Check if we have enough candles for calculation

        Returns:
            True to continue, False to skip
        """
        required = self.settings.INDICATOR_CANDLE_LOOKBACK

        if len(candles) < required:
            logger.warning(
                f"Insufficient candles: {len(candles)}/{required} "
                f"for {exchange}/{symbol}/{timeframe}"
            )
            # Continue anyway - indicators will return None if insufficient

        return True

    def _calculate_indicators(self, candles: list) -> dict[str, float]:
        """
        Calculate all indicators using polymorphism

        Uses indicator.get_results() for clean single/multi-value support

        Args:
            candles: List of candles (with gaps filled if applicable)

        Returns:
            Dict of all indicator results: {"SMA_20": 45000.5, "MACD": 123.4, ...}
        """
        results = {}

        for name, indicator in self.indicators.items():
            try:
                # Polymorphic call - works for both single/multi-value indicators
                indicator_results = indicator.get_results(candles)
                results.update(indicator_results)

            except Exception as e:
                logger.error(f"❌ Error calculating {name}: {e}", exc_info=True)

        return results
