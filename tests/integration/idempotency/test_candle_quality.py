"""
Integration tests for candle data quality (TIER 3)

Tests candle timestamp continuity and data validity.
"""

import os
import pytest
from clickhouse_driver import Client

from config.settings import get_settings, Settings


# Set environment variables for localhost
os.environ['CLICKHOUSE_HOST'] = 'localhost'
os.environ['REDIS_HOST'] = 'localhost'
os.environ['POSTGRES_HOST'] = 'localhost'

# Reset settings singleton
if hasattr(Settings, '_yaml_loaded'):
    delattr(Settings, '_yaml_loaded')


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


@pytest.mark.integration
@pytest.mark.tier3  # 🔁 TIER 3 - Quality Checks
def test_no_gaps_in_candle_timestamps(clickhouse_client):
    """Test that synced candles have minimal gaps"""
    # Check for large gaps in timestamps
    gaps = clickhouse_client.execute(
        """
        WITH ordered AS (
            SELECT
                timestamp,
                lagInFrame(timestamp) OVER (ORDER BY timestamp) as prev_timestamp
            FROM trading.candles_1m FINAL
            WHERE exchange = 'binance' AND symbol = 'BTCUSDT'
            ORDER BY timestamp
        )
        SELECT
            count() as gap_count
        FROM ordered
        WHERE dateDiff('minute', prev_timestamp, timestamp) > 2
        """
    )

    if gaps and gaps[0][0] is not None:
        gap_count = gaps[0][0]
        print(f"\nGaps > 2 minutes: {gap_count}")
        # Allow some gaps due to API limitations
        total_candles = clickhouse_client.execute(
            "SELECT count() FROM trading.candles_1m FINAL WHERE exchange = 'binance' AND symbol = 'BTCUSDT'"
        )[0][0]

        if total_candles > 0:
            gap_ratio = gap_count / total_candles
            assert gap_ratio < 0.1, f"Too many gaps: {gap_ratio:.2%}"
            print(f"  ✓ Gap ratio acceptable: {gap_ratio:.2%}")


@pytest.mark.integration
@pytest.mark.tier3  # 🔁 TIER 3 - Quality Checks
def test_candle_ohlc_relationships(clickhouse_client):
    """Test that candles have valid OHLC relationships"""
    invalid_candles = clickhouse_client.execute(
        """
        SELECT count() as invalid_count
        FROM trading.candles_1m FINAL
        WHERE high < low
           OR high < open
           OR high < close
           OR low > open
           OR low > close
           OR open <= 0
           OR close <= 0
           OR volume < 0
        """
    )

    invalid_count = invalid_candles[0][0]
    print(f"\nInvalid candles (bad OHLC): {invalid_count}")
    assert invalid_count == 0, f"Found {invalid_count} candles with invalid OHLC relationships"
    print("  ✓ All candles have valid OHLC relationships")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
