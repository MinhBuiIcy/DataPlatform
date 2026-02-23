"""
Integration test for Grafana dashboard compatibility

Tests that pipeline data is queryable for Grafana dashboards.
This validates that the Phase 2 data schema works with Grafana queries.

Requires Docker services and synced candle/indicator data.
"""

import os

import pytest
from clickhouse_driver import Client

from config.settings import Settings, get_settings


def get_indicator_value(
    clickhouse_client, exchange, symbol, timeframe, indicator_name, timestamp=None
):
    """
    Helper function to get indicator value from normalized schema.

    Schema: indicator_name | indicator_value (1 row per indicator)
    """
    query = """
        SELECT indicator_value
        FROM trading.indicators
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
        host="localhost",
        port=settings.CLICKHOUSE_PORT,
        database=settings.CLICKHOUSE_DB,
        user=settings.CLICKHOUSE_USER,
        password=settings.CLICKHOUSE_PASSWORD,
    )
    yield client
    client.disconnect()


@pytest.mark.integration
def test_pipeline_grafana_queryable(clickhouse_client):
    """Test that pipeline data is queryable for Grafana dashboards"""
    print("\n[Test] Grafana-ready queries")

    # Query 1: Latest price with indicators (normalized schema)
    # Note: With normalized schema, we pivot indicators in application layer or use subqueries
    query1 = clickhouse_client.execute(
        """
        SELECT
            c.timestamp,
            c.exchange,
            c.symbol,
            c.close as price
        FROM trading.candles_1m c
        WHERE c.exchange = 'binance'
            AND c.symbol = 'BTCUSDT'
        ORDER BY c.timestamp DESC
        LIMIT 100
        """
    )

    print(f"  Query 1 (Price Chart): {len(query1)} rows")
    assert len(query1) > 0

    # Verify we can fetch indicators for these timestamps
    if len(query1) > 0:
        sample_timestamp = query1[0][0]
        sma_20 = get_indicator_value(
            clickhouse_client, "binance", "BTCUSDT", "1m", "SMA_20", sample_timestamp
        )
        print(f"    Sample SMA_20 at {sample_timestamp}: {sma_20}")

    # Query 2: RSI for RSI panel (normalized schema)
    query2 = clickhouse_client.execute(
        """
        SELECT
            timestamp,
            exchange,
            symbol,
            indicator_value as RSI_14
        FROM trading.indicators
        WHERE exchange = 'binance'
            AND symbol = 'BTCUSDT'
            AND indicator_name = 'RSI_14'
        ORDER BY timestamp DESC
        LIMIT 100
        """
    )

    print(f"  Query 2 (RSI Panel): {len(query2)} rows")

    # Query 3: MACD histogram (requires multiple indicator fetches)
    # Get timestamps where MACD exists
    query3_timestamps = clickhouse_client.execute(
        """
        SELECT DISTINCT timestamp
        FROM trading.indicators
        WHERE exchange = 'binance'
            AND symbol = 'BTCUSDT'
            AND indicator_name = 'MACD'
        ORDER BY timestamp DESC
        LIMIT 100
        """
    )

    print(f"  Query 3 (MACD Panel): {len(query3_timestamps)} timestamps")

    # Verify we can fetch MACD components
    if len(query3_timestamps) > 0:
        sample_ts = query3_timestamps[0][0]
        macd = get_indicator_value(clickhouse_client, "binance", "BTCUSDT", "1m", "MACD", sample_ts)
        macd_signal = get_indicator_value(
            clickhouse_client, "binance", "BTCUSDT", "1m", "MACD_signal", sample_ts
        )
        macd_hist = get_indicator_value(
            clickhouse_client, "binance", "BTCUSDT", "1m", "MACD_histogram", sample_ts
        )
        print(
            f"    Sample MACD at {sample_ts}: MACD={macd}, Signal={macd_signal}, Hist={macd_hist}"
        )

    print("  ✓ All Grafana queries executable")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
