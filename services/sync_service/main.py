"""
Sync Service - Continuously sync latest klines from exchange REST API

Industry Standard Pattern:
- Scheduled job: Every 60 seconds
- Fetches latest candles via REST API (authoritative)
- Stores in ClickHouse (candles_1m, 5m, 1h)
- No gap handling (always fetch latest)

Replaces old backfill service complexity with simple scheduled sync.
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
from factory.client_factory import create_exchange_rest_api, create_timeseries_db

# Configure logging
os.makedirs("data/logs", exist_ok=True)

_fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

_console = logging.StreamHandler(sys.stdout)
_console.setLevel(logging.INFO)
_console.setFormatter(logging.Formatter(_fmt))

_file = RotatingFileHandler(
    "data/logs/sync_service_errors.log",
    maxBytes=5 * 1024 * 1024,  # 5MB
    backupCount=3,
)
_file.setLevel(logging.ERROR)
_file.setFormatter(logging.Formatter(_fmt))

logging.basicConfig(level=logging.INFO, handlers=[_console, _file])
logger = logging.getLogger(__name__)


class SyncService:
    """
    Sync Service - Continuously fetch latest klines from exchange REST API.

    Architecture:
    - Reads enabled exchanges from exchanges.yaml
    - Fetches latest N candles per timeframe (no gap detection)
    - Upserts to ClickHouse (replaces duplicates)
    - Runs every 60 seconds (configurable)

    Why this is better than backfill:
    - REST API is authoritative (not sampled WebSocket trades)
    - Simpler: no gap detection complexity
    - Predictable: scheduled, not event-driven
    """

    def __init__(self):
        self.settings = get_settings()
        self.running = False

        # Load config from sync.yaml
        self.interval_seconds = self.settings.SYNC_INTERVAL_SECONDS
        self.timeframes = self.settings.SYNC_TIMEFRAMES
        self.fetch_limit = self.settings.SYNC_FETCH_LIMIT

        # Initialize ClickHouse client
        self.db = create_timeseries_db()

    async def _sync_symbol(self, api, exchange_name: str, symbol: str, limit: int | None = None):
        """
        Sync latest klines for one symbol using a shared API client.

        Args:
            api: Shared REST API client for this exchange (rate limiter shared)
            exchange_name: Exchange name (for logging)
            symbol: Symbol to sync
            limit: Number of candles to fetch (default: from config)
        """
        fetch_limit = limit or self.fetch_limit

        for timeframe in self.timeframes:
            try:
                candles = await api.fetch_latest_klines(
                    symbol=symbol, timeframe=timeframe, limit=fetch_limit
                )

                if not candles:
                    logger.warning(f"No candles fetched for {exchange_name} {symbol} {timeframe}")
                    continue

                candle_dicts = [c.model_dump() for c in candles]
                await self.db.insert_candles(candle_dicts, timeframe)

                logger.info(
                    f"✓ Synced {len(candles)} candles for {exchange_name} {symbol} {timeframe}"
                )

            except Exception as e:
                logger.error(f"Failed to sync {exchange_name} {symbol} {timeframe}: {e}")

    async def sync_exchange_klines(self, exchange_name: str, symbol: str, limit: int | None = None):
        """
        Sync latest klines for one exchange/symbol pair.
        Creates its own API client (used by tests and one-off calls).

        Args:
            exchange_name: Exchange to sync from
            symbol: Symbol to sync
            limit: Number of candles to fetch (default: from config)
        """
        api = create_exchange_rest_api(exchange_name)
        try:
            await self._sync_symbol(api, exchange_name, symbol, limit)
        finally:
            await api.close()

    async def initial_backfill(self):
        """
        Initial backfill on startup - fetch historical data for indicators.

        Fetches N candles (enough for SMA_50, MACD, etc.) from config.
        One ccxt client per exchange so rate limiter is shared across symbols.
        Exchanges run concurrently (different APIs), symbols sequential per exchange.
        """
        from config.loader import get_enabled_exchanges

        backfill_limit = self.settings.SYNC_INITIAL_BACKFILL_LIMIT
        logger.info(f"🔄 Starting initial backfill ({backfill_limit} candles per symbol)...")

        enabled_configs = get_enabled_exchanges()

        async def backfill_exchange(exchange_name, config):
            api = create_exchange_rest_api(exchange_name)
            successes = 0
            failures = 0
            try:
                for symbol in config.symbol_list:
                    try:
                        await self._sync_symbol(api, exchange_name, symbol, backfill_limit)
                        successes += 1
                    except Exception as e:
                        logger.error(f"Backfill failed {exchange_name}/{symbol}: {e}")
                        failures += 1
            finally:
                await api.close()
            return successes, failures

        results = await asyncio.gather(
            *[backfill_exchange(name, cfg) for name, cfg in enabled_configs.items()]
        )

        total_ok = sum(r[0] for r in results)
        total_fail = sum(r[1] for r in results)
        logger.info(f"✅ Initial backfill complete: {total_ok} successful, {total_fail} failed")

    async def sync_all_exchanges(self):
        """
        Sync all enabled exchanges and symbols.

        One ccxt client per exchange so rate limiter is shared across symbols.
        Exchanges run concurrently (different APIs), symbols sequential per exchange.
        """
        from config.loader import get_enabled_exchanges

        enabled_configs = get_enabled_exchanges()

        async def sync_exchange(exchange_name, config):
            api = create_exchange_rest_api(exchange_name)
            successes = 0
            failures = 0
            try:
                for symbol in config.symbol_list:
                    try:
                        await self._sync_symbol(api, exchange_name, symbol)
                        successes += 1
                    except Exception as e:
                        logger.error(f"Sync failed {exchange_name}/{symbol}: {e}")
                        failures += 1
            finally:
                await api.close()
            return successes, failures

        results = await asyncio.gather(
            *[sync_exchange(name, cfg) for name, cfg in enabled_configs.items()]
        )

        total_ok = sum(r[0] for r in results)
        total_fail = sum(r[1] for r in results)
        logger.info(f"Sync cycle complete: {total_ok} successful, {total_fail} failed")

    async def start(self):
        """Start the sync service loop"""
        logger.info("=" * 60)
        logger.info("Sync Service started")
        logger.info("=" * 60)
        logger.info(f"  Sync interval: {self.interval_seconds}s")
        logger.info(f"  Timeframes: {', '.join(self.timeframes)}")
        logger.info(f"  Fetch limit: {self.fetch_limit} candles per sync")
        logger.info("=" * 60)

        self.running = True

        try:
            await self.db.connect()
            logger.info("✓ Connected to ClickHouse")

            # Initial backfill on startup
            await self.initial_backfill()

            while self.running:
                start_time = datetime.now(UTC)
                logger.info(f"\n=== Sync cycle started at {start_time} ===")

                try:
                    await self.sync_all_exchanges()
                except Exception as e:
                    logger.error(f"Error in sync cycle: {e}", exc_info=True)

                elapsed = (datetime.now(UTC) - start_time).total_seconds()
                logger.info(f"=== Sync cycle completed in {elapsed:.2f}s ===\n")

                # Sleep until next cycle
                sleep_time = max(0, self.interval_seconds - elapsed)
                if sleep_time > 0:
                    logger.info(f"Sleeping {sleep_time:.1f}s until next sync...")
                    await asyncio.sleep(sleep_time)

        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        except Exception as e:
            logger.error(f"Error in sync service: {e}", exc_info=True)
        finally:
            await self.stop()

    async def stop(self):
        """Graceful shutdown"""
        logger.info("Stopping Sync Service...")
        self.running = False

        if self.db:
            await self.db.close()

        logger.info("Sync Service stopped")


def signal_handler(service):
    """Handle SIGINT/SIGTERM"""

    def handler(signum, frame):
        logger.info(f"Received signal {signum}")
        service.running = False

    return handler


async def main():
    """Main entry point"""
    service = SyncService()

    signal.signal(signal.SIGINT, signal_handler(service))
    signal.signal(signal.SIGTERM, signal_handler(service))

    await service.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Goodbye!")
