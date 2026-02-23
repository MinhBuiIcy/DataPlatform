"""
Integration test for complete Phase 2 pipeline (TIER 1 CRITICAL)

Tests full data flow: Exchange REST API → Sync Service → ClickHouse → Indicator Service → Redis + ClickHouse

This is the MOST CRITICAL integration test - it validates the entire Phase 2 architecture end-to-end.
"""

import json
import os

import pytest
import redis
from clickhouse_driver import Client

from config.settings import Settings, get_settings
from services.indicator_service.main import IndicatorService
from services.sync_service.main import SyncService


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


@pytest.mark.integration
@pytest.mark.tier1  # 🔥🔥🔥 TIER 1 CRITICAL
@pytest.mark.slow
async def test_full_phase2_pipeline(clickhouse_client, redis_client, settings):
    """
    🔥🔥🔥 TIER 1 CRITICAL: Complete Phase 2 validation

    Pipeline:
    Exchange REST API → Sync Service → ClickHouse (candles)
                                      ↓
                        Indicator Service → ClickHouse (indicators) + Redis

    Steps:
    1. Clear existing data
    2. Run Sync Service (backfill + sync)
    3. Verify candles in ClickHouse
    4. Run Indicator Service
    5. Verify indicators in Redis (with TTL)
    6. Verify indicators in ClickHouse
    7. Verify data consistency
    """
    print("\n" + "=" * 60)
    print("PHASE 2 PIPELINE TEST")
    print("=" * 60)

    # Step 1: Get initial state (don't clear production data)
    print("\n[1/7] Getting initial state...")
    initial_candles = clickhouse_client.execute("SELECT count() FROM trading.candles_1m FINAL")[0][
        0
    ]
    initial_indicators = clickhouse_client.execute("SELECT count() FROM trading.indicators FINAL")[
        0
    ][0]
    print(f"  Initial candles: {initial_candles}")
    print(f"  Initial indicators: {initial_indicators}")

    # Clear Redis cache only (it's just cache, safe to clear)
    redis_client.flushdb()

    # Step 2: Run Sync Service
    print("\n[2/7] Running Sync Service (initial backfill)...")
    sync_service = SyncService()

    try:
        await sync_service.db.connect()
        await sync_service.initial_backfill()

        # Quick sync cycle
        await sync_service.sync_all_exchanges()

    finally:
        await sync_service.db.close()

    # Step 3: Verify candles in ClickHouse
    print("\n[3/7] Verifying candles in ClickHouse...")
    candle_count = clickhouse_client.execute("SELECT count() FROM trading.candles_1m FINAL")[0][0]

    print(f"  Candles after sync: {candle_count}")
    assert candle_count >= initial_candles, "Sync should not delete candles"

    # Verify candle data structure
    sample_candle = clickhouse_client.execute(
        """
        SELECT exchange, symbol, timestamp, open, high, low, close, volume
        FROM trading.candles_1m FINAL
        ORDER BY timestamp DESC
        LIMIT 1
        """
    )[0]

    exchange, symbol, timestamp, open_, high, low, close, volume = sample_candle
    print(f"  Sample candle: {exchange} {symbol} 1m")
    print(f"    OHLC: {open_}/{high}/{low}/{close}, Volume: {volume}")

    assert high >= low
    assert volume >= 0  # 0 is valid for illiquid pairs with no trades in that minute

    # Step 4: Run Indicator Service
    print("\n[4/7] Running Indicator Service...")
    indicator_service = IndicatorService()

    try:
        await indicator_service.db.connect()
        await indicator_service.cache.connect()

        # Run catch-up to process all historical candles
        await indicator_service.catch_up_indicators()

        # Run regular calculation cycle
        await indicator_service.calculate_and_store_indicators()

    finally:
        await indicator_service.stop()

    # Step 5: Verify indicators in Redis
    print("\n[5/7] Verifying indicators in Redis...")
    indicator_keys = redis_client.keys("indicators:*")

    print(f"  Cached indicators: {len(indicator_keys)}")
    assert len(indicator_keys) > 0, "No indicators cached in Redis"

    # Verify first cached indicator
    first_key = indicator_keys[0]
    cached_value = redis_client.get(first_key)
    cached_data = json.loads(cached_value)

    print(f"  Sample cache key: {first_key}")
    print(f"    Indicators: {list(cached_data['indicators'].keys())}")

    assert "timestamp" in cached_data
    assert "indicators" in cached_data
    assert len(cached_data["indicators"]) > 0

    # Verify TTL
    ttl = redis_client.ttl(first_key)
    print(f"    TTL: {ttl}s")
    assert 0 < ttl <= 60, f"TTL should be ~60s, got {ttl}s"

    # Step 6: Verify indicators in ClickHouse
    print("\n[6/7] Verifying indicators in ClickHouse...")
    indicator_count = clickhouse_client.execute("SELECT count() FROM trading.indicators FINAL")[0][
        0
    ]

    print(f"  Indicators in ClickHouse: {indicator_count}")
    assert indicator_count > 0, "No indicators in ClickHouse"

    # Verify indicator data (normalized schema)
    sample_record = clickhouse_client.execute(
        """
        SELECT exchange, symbol, timestamp
        FROM trading.indicators FINAL
        WHERE indicator_name = 'SMA_20'
        ORDER BY timestamp DESC
        LIMIT 1
        """
    )

    if len(sample_record) > 0:
        ind_exchange, ind_symbol, ind_timestamp = sample_record[0]
        ind_timeframe = "1m"  # Hardcoded - indicators are calculated from candles_1m

        # Fetch indicator values using helper
        sma_20 = get_indicator_value(
            clickhouse_client, ind_exchange, ind_symbol, ind_timeframe, "SMA_20", ind_timestamp
        )
        ema_12 = get_indicator_value(
            clickhouse_client, ind_exchange, ind_symbol, ind_timeframe, "EMA_12", ind_timestamp
        )
        rsi_14 = get_indicator_value(
            clickhouse_client, ind_exchange, ind_symbol, ind_timeframe, "RSI_14", ind_timestamp
        )
        macd = get_indicator_value(
            clickhouse_client, ind_exchange, ind_symbol, ind_timeframe, "MACD", ind_timestamp
        )

        print(f"  Sample indicator: {ind_exchange} {ind_symbol} {ind_timeframe}")
        print(f"    SMA_20: {sma_20}")
        print(f"    EMA_12: {ema_12}")
        print(f"    RSI_14: {rsi_14}")
        print(f"    MACD: {macd}")

        if sma_20 is not None:
            assert sma_20 > 0
        if rsi_14 is not None:
            assert 0 <= rsi_14 <= 100

    # Step 7: Verify data consistency
    print("\n[7/7] Verifying data consistency...")

    # Check that indicators exist for symbols with candles
    symbols_with_candles = clickhouse_client.execute(
        """
        SELECT DISTINCT exchange, symbol
        FROM trading.candles_1m FINAL
        """
    )

    symbols_with_indicators = clickhouse_client.execute(
        """
        SELECT DISTINCT exchange, symbol
        FROM trading.indicators FINAL
        """
    )

    print(f"  Symbols with candles: {len(symbols_with_candles)}")
    print(f"  Symbols with indicators: {len(symbols_with_indicators)}")

    # Should have indicators for most symbols (allowing for min_candles filter)
    assert len(symbols_with_indicators) > 0

    # Verify timestamp alignment
    latest_candle_time = clickhouse_client.execute(
        "SELECT max(timestamp) FROM trading.candles_1m FINAL"
    )[0][0]

    latest_indicator_time = clickhouse_client.execute(
        "SELECT max(timestamp) FROM trading.indicators FINAL"
    )[0][0]

    print(f"  Latest candle: {latest_candle_time}")
    print(f"  Latest indicator: {latest_indicator_time}")

    # Indicators should be close to latest candles (within reasonable time)
    if latest_candle_time and latest_indicator_time:
        time_diff = abs((latest_candle_time - latest_indicator_time).total_seconds())
        print(f"  Time difference: {time_diff}s")
        # Allow up to 1 hour difference (indicators calculated from candles)
        assert time_diff < 3600

    print("\n" + "=" * 60)
    print("✅ PHASE 2 PIPELINE TEST PASSED")
    print("=" * 60)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
