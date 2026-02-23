"""
Integration tests for Indicator Service pipeline (TIER 1 CRITICAL)

Tests end-to-end indicator calculation and storage to Redis + ClickHouse.
This validates the Phase 2 technical analysis pipeline.

Requires Docker services and synced candle data.
"""

import json
import os

import pytest
import redis
from clickhouse_driver import Client

from config.settings import Settings, get_settings
from services.indicator_service.main import IndicatorService


def get_indicator_value(
    clickhouse_client, exchange, symbol, timeframe, indicator_name, timestamp=None
):
    """
    Helper function to get indicator value from normalized schema.

    Schema: indicator_name | indicator_value (1 row per indicator)
    """
    query = """
        SELECT indicator_value
        FROM trading.indicators FINAL
        WHERE exchange = %(exchange)s
          AND symbol = %(symbol)s
          AND timeframe = %(timeframe)s
          AND indicator_name = %(indicator_name)s
    """
    params = {
        "exchange": exchange,
        "symbol": symbol,
        "timeframe": timeframe,
        "indicator_name": indicator_name,
    }

    if timestamp:
        query += " AND timestamp = %(timestamp)s"
        params["timestamp"] = timestamp
    else:
        query += " ORDER BY timestamp DESC LIMIT 1"

    result = clickhouse_client.execute(query, params)
    return result[0][0] if result else None


# Set environment variables for localhost before any imports
os.environ["CLICKHOUSE_HOST"] = "localhost"
os.environ["REDIS_HOST"] = "localhost"
os.environ["POSTGRES_HOST"] = "localhost"

# Reset settings singleton
if hasattr(Settings, "_yaml_loaded"):
    delattr(Settings, "_yaml_loaded")


@pytest.fixture(scope="module")
def settings():
    """Get application settings (with localhost override)"""
    return get_settings()


@pytest.fixture(scope="module")
def clickhouse_client(settings):
    """Create ClickHouse client"""
    client = Client(
        host="localhost",  # Hardcoded for integration tests
        port=settings.CLICKHOUSE_PORT,
        database=settings.CLICKHOUSE_DB,
        user=settings.CLICKHOUSE_USER,
        password=settings.CLICKHOUSE_PASSWORD,
    )
    yield client
    client.disconnect()


@pytest.fixture(scope="module")
def redis_client(settings):
    """Create Redis client"""
    client = redis.Redis(
        host="localhost", port=settings.REDIS_PORT, db=settings.REDIS_DB, decode_responses=True
    )
    yield client
    client.close()


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
@pytest.mark.tier1  # 🔥 TIER 1 CRITICAL
class TestIndicatorPipeline:
    """Test Indicator Service end-to-end pipeline (TIER 1 CRITICAL)"""

    @pytest.mark.asyncio
    async def test_calculate_and_store_indicators(
        self, clickhouse_client, redis_client, synced_candles
    ):
        """🔥 TIER 1 CRITICAL: Indicator calculation pipeline"""
        service = IndicatorService()

        try:
            await service.db.connect()
            await service.cache.connect()

            # Run calculation cycle
            await service.calculate_and_store_indicators()

            # Verify indicators saved to ClickHouse
            indicator_count = clickhouse_client.execute(
                "SELECT count() FROM trading.indicators FINAL"
            )[0][0]

            print(f"\nIndicators in ClickHouse: {indicator_count}")
            assert indicator_count > 0, "No indicators saved to ClickHouse"

            # Verify indicators have expected fields (using normalized schema)
            sample = clickhouse_client.execute(
                """
                SELECT DISTINCT exchange, symbol, timeframe, timestamp
                FROM trading.indicators FINAL
                ORDER BY timestamp DESC
                LIMIT 1
                """
            )

            if len(sample) > 0:
                exchange, symbol, timeframe, timestamp = sample[0]

                # Get indicator values using helper function
                sma_20 = get_indicator_value(
                    clickhouse_client, exchange, symbol, timeframe, "SMA_20", timestamp
                )
                rsi_14 = get_indicator_value(
                    clickhouse_client, exchange, symbol, timeframe, "RSI_14", timestamp
                )

                print(f"Sample indicator: {exchange} {symbol} {timeframe}")
                print(f"  SMA_20: {sma_20}")
                print(f"  RSI_14: {rsi_14}")

                if sma_20:
                    assert sma_20 > 0
                if rsi_14:
                    assert 0 <= rsi_14 <= 100

        finally:
            await service.stop()

    @pytest.mark.asyncio
    async def test_indicators_saved_to_redis_with_ttl(self, redis_client, synced_candles):
        """Test indicators saved to Redis with correct TTL"""
        service = IndicatorService()

        try:
            await service.db.connect()
            await service.cache.connect()

            # Clear Redis cache
            redis_client.flushdb()

            # Run calculation
            await service.calculate_and_store_indicators()

            # Check Redis for cached indicators
            indicator_keys = redis_client.keys("indicators:*")

            print(f"\nCached indicator keys: {len(indicator_keys)}")
            assert len(indicator_keys) > 0, "No indicators cached in Redis"

            # Verify first cached indicator
            first_key = indicator_keys[0]
            cached_value = redis_client.get(first_key)
            assert cached_value is not None

            # Parse JSON
            data = json.loads(cached_value)
            print(f"Cached indicator: {first_key}")
            print(f"  Timestamp: {data['timestamp']}")
            print(f"  Indicators: {list(data['indicators'].keys())}")

            assert "timestamp" in data
            assert "indicators" in data
            assert len(data["indicators"]) > 0

            # Verify TTL is set (around 60 seconds)
            ttl = redis_client.ttl(first_key)
            print(f"  TTL: {ttl}s")
            assert 0 < ttl <= 60, f"TTL should be ~60s, got {ttl}s"

        finally:
            await service.stop()

    @pytest.mark.asyncio
    async def test_sma_ema_rsi_macd_calculations(self, clickhouse_client, synced_candles):
        """Test SMA, EMA, RSI, MACD indicators calculated correctly"""
        service = IndicatorService()

        try:
            await service.db.connect()
            await service.cache.connect()

            # Run calculation
            await service.calculate_and_store_indicators()

            # Get latest indicator record (normalized schema)
            latest_record = clickhouse_client.execute(
                """
                SELECT exchange, symbol, timeframe, timestamp
                FROM trading.indicators FINAL
                WHERE indicator_name = 'SMA_20'
                ORDER BY timestamp DESC
                LIMIT 1
                """
            )

            if len(latest_record) > 0:
                exchange, symbol, timeframe, timestamp = latest_record[0]

                # Fetch all indicator values using helper function
                sma_20 = get_indicator_value(
                    clickhouse_client, exchange, symbol, timeframe, "SMA_20", timestamp
                )
                sma_50 = get_indicator_value(
                    clickhouse_client, exchange, symbol, timeframe, "SMA_50", timestamp
                )
                ema_12 = get_indicator_value(
                    clickhouse_client, exchange, symbol, timeframe, "EMA_12", timestamp
                )
                ema_26 = get_indicator_value(
                    clickhouse_client, exchange, symbol, timeframe, "EMA_26", timestamp
                )
                rsi_14 = get_indicator_value(
                    clickhouse_client, exchange, symbol, timeframe, "RSI_14", timestamp
                )
                macd = get_indicator_value(
                    clickhouse_client, exchange, symbol, timeframe, "MACD", timestamp
                )
                macd_signal = get_indicator_value(
                    clickhouse_client, exchange, symbol, timeframe, "MACD_signal", timestamp
                )
                macd_histogram = get_indicator_value(
                    clickhouse_client, exchange, symbol, timeframe, "MACD_histogram", timestamp
                )

                print(f"\nCalculated indicators for {exchange} {symbol} {timeframe}:")
                print(f"  SMA_20: {sma_20}")
                print(f"  SMA_50: {sma_50}")
                print(f"  EMA_12: {ema_12}")
                print(f"  EMA_26: {ema_26}")
                print(f"  RSI_14: {rsi_14}")
                print(f"  MACD: {macd}")
                print(f"  MACD_signal: {macd_signal}")
                print(f"  MACD_histogram: {macd_histogram}")

                # Verify SMA values
                if sma_20 is not None:
                    assert sma_20 > 0
                if sma_50 is not None:
                    assert sma_50 > 0

                # Verify EMA values
                if ema_12 is not None:
                    assert ema_12 > 0
                if ema_26 is not None:
                    assert ema_26 > 0

                # Verify RSI in valid range
                if rsi_14 is not None:
                    assert 0 <= rsi_14 <= 100

                # Verify MACD components
                if macd is not None and macd_signal is not None:
                    # MACD histogram = MACD - Signal
                    expected_histogram = macd - macd_signal
                    if macd_histogram is not None:
                        assert abs(macd_histogram - expected_histogram) < 0.01

        finally:
            await service.stop()

    @pytest.mark.asyncio
    async def test_indicator_calculation_with_sufficient_candles(
        self, clickhouse_client, synced_candles
    ):
        """Test indicators only calculated when sufficient candles available"""
        service = IndicatorService()

        try:
            await service.db.connect()
            await service.cache.connect()

            # Run calculation
            await service.calculate_and_store_indicators()

            # Query indicators and verify they have valid values
            # Count distinct timestamps where we have both SMA_20 and RSI_14
            valid_indicators = clickhouse_client.execute(
                """
                SELECT count()
                FROM (
                    SELECT exchange, symbol, timeframe, timestamp
                    FROM trading.indicators FINAL
                    WHERE indicator_name IN ('SMA_20', 'RSI_14')
                    GROUP BY exchange, symbol, timeframe, timestamp
                    HAVING count(DISTINCT indicator_name) = 2
                )
                """
            )[0][0]

            print(f"\nValid indicators (with both SMA_20 and RSI_14): {valid_indicators}")

            # Get total unique timestamps (not total rows!)
            total_unique_timestamps = clickhouse_client.execute(
                """
                SELECT count(DISTINCT (exchange, symbol, timeframe, timestamp))
                FROM trading.indicators FINAL
                """
            )[0][0]

            print(f"Total unique timestamps: {total_unique_timestamps}")

            # Most timestamps should have both SMA_20 and RSI_14 (allowing for edge cases)
            if total_unique_timestamps > 0:
                valid_ratio = valid_indicators / total_unique_timestamps
                print(f"Valid ratio: {valid_ratio:.2%}")
                assert valid_ratio > 0.5, f"Too many invalid indicators: {valid_ratio:.2%}"

        finally:
            await service.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
