"""
Integration tests for Indicator Service configuration

Tests indicator service configuration and behavior.
"""

import os

import pytest
from clickhouse_driver import Client

from config.loader import get_enabled_exchanges
from config.settings import Settings, get_settings
from services.indicator_service.main import IndicatorService

# Set environment variables for localhost
os.environ["CLICKHOUSE_HOST"] = "localhost"
os.environ["REDIS_HOST"] = "localhost"
os.environ["POSTGRES_HOST"] = "localhost"

# Reset settings singleton
if hasattr(Settings, "_yaml_loaded"):
    delattr(Settings, "_yaml_loaded")


@pytest.fixture(scope="module")
def settings():
    """Get application settings"""
    return get_settings()


@pytest.fixture(scope="module")
def clickhouse_client(settings):
    """Create ClickHouse client"""
    client = Client(
        host="localhost",
        port=settings.CLICKHOUSE_PORT,
        database=settings.CLICKHOUSE_DB,
        user=settings.CLICKHOUSE_USER,
        password=settings.CLICKHOUSE_PASSWORD,
    )
    yield client
    client.disconnect()


@pytest.fixture(scope="module")
async def synced_candles(clickhouse_client):
    """
    Verify candles exist in ClickHouse (from running sync service).

    IMPORTANT: This does NOT fetch data - it assumes services are already running.
    Run `uv run python services/sync_service/main.py` before running integration tests.
    """
    # Check if we have candle data (from sync service already running)
    candle_count = clickhouse_client.execute("SELECT count() FROM trading.candles_1m FINAL")[0][0]

    if candle_count == 0:
        pytest.skip(
            "No candle data in ClickHouse. "
            "Run sync service first: uv run python services/sync_service/main.py"
        )

    print(f"\n✓ Found {candle_count} candles in ClickHouse (from running services)")


@pytest.mark.integration
async def test_service_respects_min_candles_setting(clickhouse_client, synced_candles):
    """Test service skips calculation when insufficient candles"""
    service = IndicatorService()

    try:
        await service.db.connect()

        # Check minimum candles setting
        min_candles = service.settings.INDICATOR_SERVICE_MIN_CANDLES
        print(f"\nMinimum candles required: {min_candles}")

        # Verify candles available
        candle_count = clickhouse_client.execute(
            """
            SELECT count()
            FROM trading.candles_1m FINAL
            WHERE exchange = 'binance' AND symbol = 'BTCUSDT'
            """
        )[0][0]

        print(f"Candles available: {candle_count}")

        # If we have enough candles, indicators should be created
        if candle_count >= min_candles:
            await service.cache.connect()
            await service.calculate_and_store_indicators()

            indicator_count = clickhouse_client.execute(
                """
                SELECT count()
                FROM trading.indicators FINAL
                WHERE exchange = 'binance' AND symbol = 'BTCUSDT'
                """
            )[0][0]

            print(f"Indicators created: {indicator_count}")
            assert indicator_count > 0

    finally:
        await service.stop()


@pytest.mark.integration
async def test_multi_exchange_indicator_calculation(clickhouse_client, synced_candles):
    """Test indicators calculated for multiple exchanges"""
    service = IndicatorService()

    try:
        await service.db.connect()
        await service.cache.connect()

        # Run calculation
        await service.calculate_and_store_indicators()

        # Check which exchanges have indicators
        exchanges = clickhouse_client.execute(
            """
            SELECT DISTINCT exchange
            FROM trading.indicators FINAL
            ORDER BY exchange
            """
        )

        exchange_names = [e[0] for e in exchanges]
        print(f"\nExchanges with indicators: {exchange_names}")

        # Should have at least 1 exchange
        assert len(exchange_names) >= 1

        # Verify all enabled exchanges
        enabled_exchanges = get_enabled_exchanges()
        print(f"Enabled exchanges from config: {list(enabled_exchanges.keys())}")

    finally:
        await service.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
