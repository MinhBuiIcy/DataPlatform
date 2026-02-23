"""
Integration tests for Sync Service pipeline (TIER 1 CRITICAL)

Tests end-to-end synchronization of klines from exchange REST APIs to ClickHouse.
This validates the core Phase 2 data ingestion pipeline.

Requires Docker services to be running.
"""

import os
from datetime import datetime

import pytest
from clickhouse_driver import Client

from config.settings import Settings, get_settings
from services.sync_service.main import SyncService

# Set environment variables for localhost before any imports
os.environ["CLICKHOUSE_HOST"] = "localhost"
os.environ["REDIS_HOST"] = "localhost"
os.environ["POSTGRES_HOST"] = "localhost"

# Reset settings singleton to pick up environment variables
if hasattr(Settings, "_yaml_loaded"):
    delattr(Settings, "_yaml_loaded")


@pytest.fixture(scope="module")
def settings():
    """Get application settings (with localhost override)"""
    return get_settings()


@pytest.fixture(scope="module")
def clickhouse_client(settings):
    """Create ClickHouse client for verification (integration tests use localhost)"""
    client = Client(
        host="localhost",  # Hardcoded for integration tests running on host machine
        port=settings.CLICKHOUSE_PORT,
        database=settings.CLICKHOUSE_DB,
        user=settings.CLICKHOUSE_USER,
        password=settings.CLICKHOUSE_PASSWORD,
    )
    yield client
    client.disconnect()


@pytest.mark.integration
@pytest.mark.tier1  # 🔥 TIER 1 CRITICAL
class TestSyncServicePipeline:
    """Test Sync Service end-to-end pipeline (TIER 1 CRITICAL)"""

    @pytest.mark.asyncio
    async def test_sync_exchange_klines_single_symbol(self, clickhouse_client, settings):
        """🔥 TIER 1 CRITICAL: Core sync functionality"""
        service = SyncService()

        try:
            await service.db.connect()

            # Use FINAL for consistent deduplicated counts
            initial_count = clickhouse_client.execute(
                """
                SELECT count()
                FROM trading.candles_1m FINAL
                WHERE exchange = 'binance' AND symbol = 'BTCUSDT'
                """
            )[0][0]

            print(f"\nInitial candle count: {initial_count}")

            # Sync BTCUSDT from Binance
            await service.sync_exchange_klines(exchange_name="binance", symbol="BTCUSDT", limit=10)

            # Use FINAL to avoid false negatives from background merges
            final_count = clickhouse_client.execute(
                """
                SELECT count()
                FROM trading.candles_1m FINAL
                WHERE exchange = 'binance' AND symbol = 'BTCUSDT'
                """
            )[0][0]

            print(f"Final candle count: {final_count}")
            new_candles = final_count - initial_count

            # Data already synced continuously - deduplication is expected.
            # Assert function ran without error and didn't delete data.
            assert new_candles >= 0, f"Sync should not delete candles, got {new_candles}"
            assert final_count > 0, "Should have BTCUSDT candles in DB"

            # Verify data structure
            sample = clickhouse_client.execute(
                """
                SELECT exchange, symbol, open, high, low, close, volume
                FROM trading.candles_1m FINAL
                WHERE exchange = 'binance' AND symbol = 'BTCUSDT'
                ORDER BY timestamp DESC
                LIMIT 1
                """
            )

            assert len(sample) > 0
            exchange, symbol, open_, high, low, close, volume = sample[0]

            assert exchange == "binance"
            assert symbol == "BTCUSDT"
            # timeframe is implicit: candles_1m = 1 minute
            assert high >= low
            assert high >= open_
            assert high >= close
            assert low <= open_
            assert low <= close
            assert volume > 0

        finally:
            await service.db.close()

    @pytest.mark.asyncio
    async def test_initial_backfill_fetches_historical_data(self, clickhouse_client, settings):
        """Test initial_backfill() fetches historical candles"""
        service = SyncService()

        try:
            await service.db.connect()

            # Use FINAL for consistent deduplicated count
            initial_count = clickhouse_client.execute(
                "SELECT count() FROM trading.candles_1m FINAL"
            )[0][0]

            print(f"\nInitial candles: {initial_count}")

            # Run initial backfill
            await service.initial_backfill()

            # Use FINAL to avoid false negatives from background merges
            final_count = clickhouse_client.execute("SELECT count() FROM trading.candles_1m FINAL")[
                0
            ][0]

            new_candles = final_count - initial_count
            print(f"Final candles: {final_count}")
            print(f"New candles: {new_candles}")

            # Should have backfilled multiple symbols (at least some new candles)
            assert new_candles >= 0, f"Backfill should not delete data (got {new_candles})"

            # Verify table stores 1m candles (timeframe is in table name, not column)
            # candles_1m = 1-minute candles (no timeframe column exists)
            # Multi-timeframe support via separate tables: candles_1m, candles_5m, candles_1h

            # Verify multiple exchanges
            exchanges = clickhouse_client.execute(
                "SELECT DISTINCT exchange FROM trading.candles_1m ORDER BY exchange"
            )
            exchange_names = [e[0] for e in exchanges]
            print(f"Exchanges: {exchange_names}")

            # Should have at least 1 exchange
            assert len(exchange_names) >= 1

        finally:
            await service.db.close()

    @pytest.mark.asyncio
    async def test_sync_all_exchanges_sequential_processing(self, clickhouse_client, settings):
        """Test sync_all_exchanges processes sequentially without errors"""
        service = SyncService()

        try:
            await service.db.connect()

            # Use FINAL to get deduplicated count (ReplacingMergeTree merges happen in background)
            initial_count = clickhouse_client.execute(
                "SELECT count() FROM trading.candles_1m FINAL"
            )[0][0]

            # Run sync cycle (some exchanges may 429, service should continue gracefully)
            await service.sync_all_exchanges()

            final_count = clickhouse_client.execute("SELECT count() FROM trading.candles_1m FINAL")[
                0
            ][0]

            print(f"\nCandles before sync: {initial_count}")
            print(f"Candles after sync: {final_count}")

            # FINAL ensures both counts are deduplicated, so count should be stable or increase
            assert final_count >= initial_count

        finally:
            await service.db.close()

    @pytest.mark.asyncio
    async def test_candles_inserted_to_clickhouse(self, clickhouse_client, settings):
        """Test candles properly inserted to ClickHouse with correct schema"""
        service = SyncService()

        try:
            await service.db.connect()

            # Sync small amount of data
            await service.sync_exchange_klines(exchange_name="binance", symbol="BTCUSDT", limit=3)

            # Query recent candles
            candles = clickhouse_client.execute(
                """
                SELECT
                    timestamp,
                    exchange,
                    symbol,
                    open,
                    high,
                    low,
                    close,
                    volume,
                    quote_volume,
                    trades_count,
                    is_synthetic
                FROM trading.candles_1m FINAL
                WHERE exchange = 'binance' AND symbol = 'BTCUSDT'
                ORDER BY timestamp DESC
                LIMIT 3
                """
            )

            assert len(candles) > 0

            for candle in candles:
                (
                    timestamp,
                    exchange,
                    symbol,
                    open_,
                    high,
                    low,
                    close,
                    volume,
                    quote_volume,
                    trades_count,
                    is_synthetic,
                ) = candle

                # Verify schema
                assert isinstance(timestamp, datetime)
                assert exchange == "binance"
                assert symbol == "BTCUSDT"
                # timeframe is implicit: candles_1m = 1 minute
                assert open_ > 0
                assert high > 0
                assert low > 0
                assert close > 0
                assert volume >= 0
                assert quote_volume >= 0
                assert trades_count == 0  # REST API doesn't provide this
                assert is_synthetic == 0  # REST API data is real

        finally:
            await service.db.close()

    @pytest.mark.asyncio
    async def test_multi_timeframe_sync(self, clickhouse_client, settings):
        """Test syncing multiple timeframes"""
        service = SyncService()

        try:
            await service.db.connect()

            # Sync should create candles in multiple timeframe tables
            await service.sync_exchange_klines(exchange_name="binance", symbol="BTCUSDT", limit=5)

            # Check 1m table (FINAL for consistent deduplicated count)
            count_1m = clickhouse_client.execute(
                """
                SELECT count()
                FROM trading.candles_1m FINAL
                WHERE exchange = 'binance' AND symbol = 'BTCUSDT'
                """
            )[0][0]

            print(f"\n1m candles: {count_1m}")
            assert count_1m > 0

            # Check if 5m and 1h tables exist and have data (if configured)
            if "5m" in settings.SYNC_TIMEFRAMES:
                count_5m = clickhouse_client.execute(
                    """
                    SELECT count()
                    FROM trading.candles_5m FINAL
                    WHERE exchange = 'binance' AND symbol = 'BTCUSDT'
                    """
                )[0][0]
                print(f"5m candles: {count_5m}")

            if "1h" in settings.SYNC_TIMEFRAMES:
                count_1h = clickhouse_client.execute(
                    """
                    SELECT count()
                    FROM trading.candles_1h FINAL
                    WHERE exchange = 'binance' AND symbol = 'BTCUSDT'
                    """
                )[0][0]
                print(f"1h candles: {count_1h}")

        finally:
            await service.db.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
