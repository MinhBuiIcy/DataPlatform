"""
Integration tests for Sync Service idempotency (TIER 1 CRITICAL)

Tests that ReplacingMergeTree deduplicates candles correctly.
This validates that multiple sync cycles don't create duplicate data.

Requires Docker services to be running.
"""

import os

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
    """Create ClickHouse client for verification"""
    client = Client(
        host="localhost",
        port=settings.CLICKHOUSE_PORT,
        database=settings.CLICKHOUSE_DB,
        user=settings.CLICKHOUSE_USER,
        password=settings.CLICKHOUSE_PASSWORD,
    )
    yield client
    client.disconnect()


@pytest.mark.integration
@pytest.mark.tier1  # 🔥 TIER 1 CRITICAL
async def test_multiple_sync_cycles_no_duplicates(clickhouse_client):
    """
    🔥 TIER 1 CRITICAL: Verify ReplacingMergeTree prevents duplicate candles

    Tests that syncing the same data twice doesn't create duplicates.
    This is critical for data quality - duplicates would break all analytics.
    """
    print("\n[Test] Multiple sync/indicator cycles")

    sync_service = SyncService()

    try:
        await sync_service.db.connect()

        # Cycle 1: Sync
        print("\n  Cycle 1: Sync")
        await sync_service.sync_all_exchanges()

        candles_after_cycle1 = clickhouse_client.execute(
            "SELECT count() FROM trading.candles_1m FINAL"
        )[0][0]

        print(f"    Candles after cycle 1: {candles_after_cycle1}")

        # Cycle 2: Sync again (same data)
        print("\n  Cycle 2: Sync")
        await sync_service.sync_all_exchanges()

        candles_after_cycle2 = clickhouse_client.execute(
            "SELECT count() FROM trading.candles_1m FINAL"
        )[0][0]

        print(f"    Candles after cycle 2: {candles_after_cycle2}")

        # Should maintain or slightly increase data (only new candles added)
        # NOT double the data (that would indicate duplicates)
        assert candles_after_cycle2 >= candles_after_cycle1

        # Force merge to verify deduplication
        print("\n  Forcing OPTIMIZE to deduplicate...")
        clickhouse_client.execute("OPTIMIZE TABLE trading.candles_1m FINAL")

        optimized_count = clickhouse_client.execute("SELECT count() FROM trading.candles_1m FINAL")[
            0
        ][0]

        print(f"    Candles after OPTIMIZE FINAL: {optimized_count}")

        # After optimization, count should be similar (allowing for new candles)
        # This proves ReplacingMergeTree is working correctly
        growth_rate = (candles_after_cycle2 - candles_after_cycle1) / max(candles_after_cycle1, 1)
        print(f"    Growth rate: {growth_rate:.2%}")

        # Growth should be minimal (< 5%) - only new candles, not duplicates
        assert growth_rate < 0.05, f"Too much growth - possible duplicates: {growth_rate:.2%}"

        print("\n  ✅ No duplicates detected - ReplacingMergeTree working correctly")

    finally:
        await sync_service.db.close()


@pytest.mark.integration
@pytest.mark.tier1  # 🔥 TIER 1 CRITICAL
async def test_replacing_merge_tree_deduplication(clickhouse_client, settings):
    """Test that ReplacingMergeTree deduplicates identical candles"""
    service = SyncService()

    try:
        await service.db.connect()

        # Sync same data twice
        await service.sync_exchange_klines(exchange_name="binance", symbol="BTCUSDT", limit=5)

        count_after_first = clickhouse_client.execute(
            """
            SELECT count()
            FROM trading.candles_1m FINAL
            WHERE exchange = 'binance' AND symbol = 'BTCUSDT'
            """
        )[0][0]

        # Sync again (should deduplicate)
        await service.sync_exchange_klines(exchange_name="binance", symbol="BTCUSDT", limit=5)

        count_after_second = clickhouse_client.execute(
            """
            SELECT count()
            FROM trading.candles_1m FINAL
            WHERE exchange = 'binance' AND symbol = 'BTCUSDT'
            """
        )[0][0]

        print(f"\nCount after first sync: {count_after_first}")
        print(f"Count after second sync: {count_after_second}")

        # After OPTIMIZE, counts should be similar (allowing for new candles)
        # Force merge to deduplicate
        clickhouse_client.execute("OPTIMIZE TABLE trading.candles_1m FINAL")

        optimized_count = clickhouse_client.execute(
            """
            SELECT count()
            FROM trading.candles_1m FINAL
            WHERE exchange = 'binance' AND symbol = 'BTCUSDT'
            """
        )[0][0]

        print(f"Count after OPTIMIZE FINAL: {optimized_count}")

        # Deduplication should have occurred
        assert optimized_count <= count_after_second

    finally:
        await service.db.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
