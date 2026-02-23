"""
Indicator Service - Scheduled Calculation (Phase 2)

Industry Standard Pattern:
- Scheduled job: Every 60 seconds (+ 10s delay after Sync Service)
- Reads candles from ClickHouse (populated by Sync Service)
- Calculates indicators for each candle
- Stores in ClickHouse indicators table
- NO gap handling (Sync Service ensures complete data)
- NO Kafka events (scheduled, not event-driven)

Replaces complex event-driven architecture with simple scheduled jobs.
"""

import asyncio
import logging
import os
import signal
import sys
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import get_settings
from factory.client_factory import create_cache_client, create_timeseries_db
from services.indicator_service.calculator import IndicatorCalculator
from services.indicator_service.persistence import IndicatorPersistence

# Configure logging
os.makedirs("data/logs", exist_ok=True)

_fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

_console = logging.StreamHandler(sys.stdout)
_console.setLevel(logging.INFO)
_console.setFormatter(logging.Formatter(_fmt))

_file = RotatingFileHandler(
    "data/logs/indicator_service_errors.log",
    maxBytes=5 * 1024 * 1024,  # 5MB
    backupCount=3,
)
_file.setLevel(logging.ERROR)
_file.setFormatter(logging.Formatter(_fmt))

logging.basicConfig(level=logging.INFO, handlers=[_console, _file])
logger = logging.getLogger(__name__)


class IndicatorService:
    """
    Indicator Service - Scheduled calculation from ClickHouse.

    Runs every 60 seconds (+ 10s delay after Sync Service).

    Flow:
    1. Query ClickHouse for latest candles (last 2 minutes)
    2. Calculate indicators for each candle
    3. Store in ClickHouse indicators table

    No gap handling - Sync Service ensures data is complete.
    """

    def __init__(self):
        self.settings = get_settings()
        self.running = False

        # Initialize clients
        logger.info("🔧 Initializing clients...")
        self.db = create_timeseries_db()
        self.cache = create_cache_client()

        # Initialize components
        self.persistence = IndicatorPersistence(self.db, self.cache)
        self.calculator = IndicatorCalculator(
            db=self.db,
            persistence=self.persistence,
        )

    async def calculate_and_store_indicators(self):
        """
        Fetch latest candles and calculate indicators.

        Queries ClickHouse for latest candles per exchange/symbol,
        calculates all configured indicators, stores results.
        """
        from config.loader import get_enabled_exchanges

        # Get all enabled exchange/symbol pairs
        enabled_configs = get_enabled_exchanges()

        try:
            # Process each exchange/symbol/timeframe combination
            for exchange_name, config in enabled_configs.items():
                for symbol_obj in config.symbols:
                    symbol = symbol_obj.native  # e.g., "BTCUSDT"

                    for timeframe in self.settings.SYNC_TIMEFRAMES:
                        try:
                            # Query latest candles for this symbol
                            candles = await self.db.query_candles(
                                exchange=exchange_name,
                                symbol=symbol,
                                timeframe=timeframe,
                                limit=self.settings.INDICATOR_CANDLE_LOOKBACK,
                            )

                            min_candles = self.settings.INDICATOR_SERVICE_MIN_CANDLES
                            if not candles or len(candles) < min_candles:
                                continue

                            # Process with all candles (calculator needs history for indicators)
                            latest_candle = candles[-1]
                            await self.calculator.process_candle_with_history(
                                latest_candle, candles
                            )

                        except Exception as e:
                            logger.error(
                                f"Failed to process {exchange_name}/{symbol}/{timeframe}: {e}"
                            )

        except Exception as e:
            logger.error(f"Failed to calculate indicators: {e}")
            raise

    async def catch_up_indicators(self):
        """
        Catch-up mode: Calculate indicators for ALL existing candles on startup.

        This ensures backfilled candles have indicators calculated.
        """
        from config.loader import get_enabled_exchanges

        logger.info("🔄 Starting catch-up: Processing all existing candles...")

        enabled_configs = get_enabled_exchanges()
        total_processed = 0

        catch_up_limit = self.settings.INDICATOR_SERVICE_CATCH_UP_LIMIT
        min_candles = self.settings.INDICATOR_SERVICE_MIN_CANDLES

        for exchange_name, config in enabled_configs.items():
            for symbol_obj in config.symbols:
                symbol = symbol_obj.native

                for timeframe in self.settings.SYNC_TIMEFRAMES:
                    try:
                        # Get ALL candles for this symbol
                        candles = await self.db.query_candles(
                            exchange=exchange_name,
                            symbol=symbol,
                            timeframe=timeframe,
                            limit=catch_up_limit,
                        )

                        if len(candles) < min_candles:
                            continue

                        # Process each candle (skip if indicator already exists)
                        for i in range(len(candles)):
                            if i < (min_candles - 1):  # Need at least min_candles for indicators
                                continue

                            # Get historical window for this candle
                            historical_candles = candles[max(0, i - 99) : i + 1]
                            current_candle = candles[i]

                            # Calculate indicators
                            await self.calculator.process_candle_with_history(
                                current_candle, historical_candles
                            )
                            total_processed += 1

                        logger.info(
                            f"✓ Catch-up: {len(candles)} candles for "
                            f"{exchange_name}/{symbol}/{timeframe}"
                        )

                    except Exception as e:
                        logger.error(
                            f"Catch-up failed for {exchange_name}/{symbol}/{timeframe}: {e}"
                        )

        logger.info(f"✅ Catch-up complete: Processed {total_processed} candles")

    async def start(self):
        """Start the indicator service loop"""
        interval = self.settings.INDICATOR_SERVICE_INTERVAL_SECONDS
        initial_delay = self.settings.INDICATOR_SERVICE_INITIAL_DELAY_SECONDS

        logger.info("=" * 60)
        logger.info("Indicator Service started (scheduled mode)")
        logger.info("=" * 60)
        logger.info(f"  Interval: {interval}s (+ {initial_delay}s initial delay)")
        logger.info(f"  Timeframes: {', '.join(self.settings.SYNC_TIMEFRAMES)}")
        logger.info("=" * 60)

        self.running = True

        try:
            # Connect to all clients
            await self.db.connect()
            logger.info("✅ Connected to ClickHouse")

            await self.cache.connect()
            logger.info("✅ Connected to Redis")

            # Initial delay: wait for Sync Service to backfill
            logger.info(f"⏳ Initial {initial_delay}s delay (waiting for Sync Service backfill)...")
            await asyncio.sleep(initial_delay)

            # Catch-up: Process all existing candles
            if self.settings.INDICATOR_SERVICE_CATCH_UP_ENABLED:
                await self.catch_up_indicators()

            while self.running:
                start_time = datetime.now(UTC)
                logger.info(f"\n=== Indicator calculation started at {start_time} ===")

                try:
                    await self.calculate_and_store_indicators()
                except Exception as e:
                    logger.error(f"Error in calculation cycle: {e}", exc_info=True)

                elapsed = (datetime.now(UTC) - start_time).total_seconds()
                logger.info(f"=== Calculation completed in {elapsed:.2f}s ===\n")

                # Sleep until next cycle
                sleep_time = max(0, interval - elapsed)
                if sleep_time > 0:
                    logger.info(f"Sleeping {sleep_time:.1f}s until next calculation...")
                    await asyncio.sleep(sleep_time)

        except KeyboardInterrupt:
            logger.info("⚠️ Received interrupt signal")
        except Exception as e:
            logger.error(f"❌ Fatal error: {e}", exc_info=True)
        finally:
            await self.stop()

    async def stop(self):
        """Graceful shutdown"""
        logger.info("🛑 Stopping Indicator Service...")
        self.running = False

        if self.db:
            await self.db.close()
        if self.cache:
            await self.cache.close()

        logger.info("✅ Indicator Service stopped")


def signal_handler(service):
    """Handle SIGINT/SIGTERM"""

    def handler(signum, frame):
        logger.info(f"Received signal {signum}")
        service.running = False

    return handler


async def main():
    """Main entry point"""
    service = IndicatorService()

    signal.signal(signal.SIGINT, signal_handler(service))
    signal.signal(signal.SIGTERM, signal_handler(service))

    await service.start()


if __name__ == "__main__":
    # Ensure log directory exists
    log_dir = Path("data/logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Goodbye!")
