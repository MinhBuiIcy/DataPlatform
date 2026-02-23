"""
Integration test for WebSocket → Redis ingestion

Tests WebSocket price updates are written to Redis.
This validates the Phase 2 real-time price pipeline (separate from candles).

Requires Docker services running and WebSocket service active.
"""

import os

import pytest
import redis as redis_lib

from config.settings import Settings, get_settings

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
def redis_client(settings):
    """Create Redis client"""
    client = redis_lib.Redis(
        host="localhost", port=settings.REDIS_PORT, db=settings.REDIS_DB, decode_responses=True
    )
    yield client
    client.close()


@pytest.mark.integration
def test_websocket_writes_to_redis(redis_client):
    """
    Test WebSocket service writes latest_price keys to Redis

    Phase 2 Architecture:
    - WebSocket writes ONLY to Redis (latest_price keys)
    - Sync Service writes candles to ClickHouse (from REST API)

    NOTE: This test requires WebSocket service to be running:
    uv run python services/market_data_ingestion/main.py
    """
    print("\n🔍 Checking Redis latest_price keys...")

    # Check if any latest_price keys exist
    keys = redis_client.keys("latest_price:*")

    if len(keys) == 0:
        pytest.skip(
            "No latest_price keys found in Redis. "
            "Start WebSocket service: uv run python services/market_data_ingestion/main.py"
        )

    print(f"  ✓ Found {len(keys)} latest_price keys")

    # Verify data structure - check some sample keys
    print("  Sample latest_price keys:")
    for key in list(keys)[:5]:
        key_str = key.decode() if isinstance(key, bytes) else key
        price = redis_client.get(key_str)
        if price:
            price_str = price.decode() if isinstance(price, bytes) else price
            print(f"    {key_str}: {price_str}")

            # Parse key format: latest_price:exchange:symbol
            parts = key_str.split(":")
            if len(parts) == 3:
                _, exchange, symbol = parts

                # Verify data structure
                assert exchange in ["binance", "coinbase", "kraken"]
                assert len(symbol) > 0  # Symbol should be non-empty
                assert float(price_str) > 0

    print("  ✓ All price keys have valid format and values")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
