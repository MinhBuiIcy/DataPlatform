"""
Integration tests for indicator data quality (TIER 3)

Tests that calculated indicators are within reasonable ranges.
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
def test_indicator_values_within_reasonable_ranges(clickhouse_client):
    """Test that calculated indicators are within reasonable ranges"""
    stats = clickhouse_client.execute(
        """
        SELECT
            avg(indicator_value) as avg_rsi,
            min(indicator_value) as min_rsi,
            max(indicator_value) as max_rsi,
            count() as total
        FROM trading.indicators FINAL
        WHERE indicator_name = 'RSI_14'
        """
    )

    if stats and stats[0][3] > 0:  # If we have data
        avg_rsi, min_rsi, max_rsi, total = stats[0]

        print(f"\nRSI statistics:")
        print(f"  Average: {avg_rsi:.2f}")
        print(f"  Min: {min_rsi:.2f}")
        print(f"  Max: {max_rsi:.2f}")
        print(f"  Total: {total}")

        # RSI should always be 0-100
        assert 0 <= min_rsi <= 100
        assert 0 <= max_rsi <= 100
        assert 0 <= avg_rsi <= 100
        print("  ✓ RSI values within valid range (0-100)")


@pytest.mark.integration
@pytest.mark.tier3  # 🔁 TIER 3 - Quality Checks
def test_sma_values_positive(clickhouse_client):
    """Test that SMA values are positive (prices can't be negative)"""
    invalid_sma = clickhouse_client.execute(
        """
        SELECT count() as invalid_count
        FROM trading.indicators FINAL
        WHERE indicator_name LIKE 'SMA_%'
          AND indicator_value <= 0
        """
    )

    invalid_count = invalid_sma[0][0]
    print(f"\nInvalid SMA values (<=0): {invalid_count}")
    assert invalid_count == 0, f"Found {invalid_count} SMA indicators with non-positive values"
    print("  ✓ All SMA values are positive")


@pytest.mark.integration
@pytest.mark.tier3  # 🔁 TIER 3 - Quality Checks
def test_ema_values_positive(clickhouse_client):
    """Test that EMA values are positive (prices can't be negative)"""
    invalid_ema = clickhouse_client.execute(
        """
        SELECT count() as invalid_count
        FROM trading.indicators FINAL
        WHERE indicator_name LIKE 'EMA_%'
          AND indicator_value <= 0
        """
    )

    invalid_count = invalid_ema[0][0]
    print(f"\nInvalid EMA values (<=0): {invalid_count}")
    assert invalid_count == 0, f"Found {invalid_count} EMA indicators with non-positive values"
    print("  ✓ All EMA values are positive")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
