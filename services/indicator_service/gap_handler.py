"""
Gap Handler - Wrapper for gap detection and filling

Responsibilities:
- Gap detection in candle series
- Gap filling with synthetic candles
- Gap ratio validation
- Logging gap details

Uses core utilities:
- core.utils.gap_handling.detect_gaps()
- core.utils.gap_handling.fill_gaps()
- core.utils.gap_handling.parse_timeframe()
"""

import logging

from config.settings import get_settings
from core.utils.gap_handling import detect_gaps, fill_gaps, parse_timeframe

logger = logging.getLogger(__name__)


class GapHandler:
    """Handle gap detection and filling for candle data"""

    def __init__(self):
        self.settings = get_settings()

    def process_candles(
        self,
        candles: list,
        timeframe: str,
        exchange: str,
        symbol: str,
    ) -> list | None:
        """
        Process candles with gap detection and filling

        Args:
            candles: List of candles
            timeframe: Timeframe string (1m, 5m, 1h, etc.)
            exchange: Exchange name
            symbol: Trading pair

        Returns:
            List of candles with gaps filled, or None if should skip calculation
        """
        if not candles:
            return candles

        # Detect gaps
        interval_minutes = parse_timeframe(timeframe)
        gaps = detect_gaps(candles, interval_minutes)

        if not gaps:
            return candles

        # Log gap detection
        self._log_gaps(gaps, exchange, symbol, timeframe)

        # Check if gap filling is enabled
        if not self.settings.INDICATOR_ENABLE_GAP_FILLING:
            logger.warning(
                f"Gap filling disabled, skipping calculation for {exchange}/{symbol}/{timeframe}"
            )
            return None

        # Fill gaps
        filled_candles = fill_gaps(candles, gaps)

        # Validate gap ratio
        if not self._validate_gap_ratio(filled_candles, exchange, symbol, timeframe):
            return None

        return filled_candles

    def _log_gaps(self, gaps: list, exchange: str, symbol: str, timeframe: str) -> None:
        """Log gap detection details"""
        total_missing = sum(g.missing_count for g in gaps)
        logger.warning(
            f"📊 Gap detected in {exchange}/{symbol}/{timeframe}: "
            f"{len(gaps)} gaps, {total_missing} missing candles"
        )

        for gap in gaps:
            logger.debug(f"  Gap: {gap.start_time} to {gap.end_time} ({gap.missing_count} candles)")

    def _validate_gap_ratio(
        self,
        candles: list,
        exchange: str,
        symbol: str,
        timeframe: str,
    ) -> bool:
        """
        Validate gap ratio is below threshold

        Args:
            candles: List of candles (with synthetic candles)
            exchange: Exchange name
            symbol: Trading pair
            timeframe: Timeframe string

        Returns:
            True if valid, False if gap ratio too high
        """
        synthetic_count = sum(1 for c in candles if c.is_synthetic)
        gap_ratio = synthetic_count / len(candles)

        if gap_ratio > self.settings.INDICATOR_MAX_GAP_RATIO:
            logger.error(
                f"⚠️ High gap ratio: {gap_ratio:.2%} for {exchange}/{symbol}/{timeframe} "
                f"(threshold: {self.settings.INDICATOR_MAX_GAP_RATIO:.2%})"
            )
            return False

        return True
