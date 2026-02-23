"""
Integration tests for Redis cache consistency (TIER 3)

Tests Redis cache data format and consistency.
"""

import json
import os
import pytest
import redis as redis_lib

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
def redis_client(settings):
    """Create Redis client"""
    client = redis_lib.Redis(host="localhost", port=settings.REDIS_PORT, db=settings.REDIS_DB, decode_responses=True)
    yield client
    client.close()


@pytest.mark.integration
@pytest.mark.tier3  # 🔁 TIER 3 - Quality Checks
def test_redis_cache_format(redis_client):
    """Test Redis cache data format - Phase 2: WebSocket → Redis only"""
    print("\n🔄 Testing Redis latest_price format...")

    # Phase 2: WebSocket writes to Redis only, not ClickHouse
    # Check if any latest_price keys exist
    keys = redis_client.keys("latest_price:*")

    if keys:
        # Get first key and verify format
        test_key = keys[0]
        test_key_str = test_key.decode() if isinstance(test_key, bytes) else test_key

        redis_data = redis_client.get(test_key_str)
        assert redis_data is not None, f"Key exists but no value: {test_key_str}"

        # Convert to string
        redis_str = redis_data.decode() if isinstance(redis_data, bytes) else redis_data

        # Parse price value (Phase 2: StreamProcessor writes float directly)
        try:
            redis_price = float(redis_str)
            print(f"  ✓ {test_key_str}: ${redis_price}")
            assert redis_price > 0, "Price should be positive"
        except (ValueError, TypeError) as e:
            # Fallback: Try parsing as JSON (some tests might write JSON)
            try:
                redis_json = json.loads(redis_str)
                redis_price = float(redis_json.get("price", 0))
                print(f"  ✓ {test_key_str}: ${redis_price} (JSON format)")
                assert redis_price > 0, "Price should be positive"
            except:
                raise AssertionError(f"Invalid Redis price format: {redis_str}")
    else:
        pytest.skip("No latest_price keys found (WebSocket service not running)")


@pytest.mark.integration
@pytest.mark.tier3  # 🔁 TIER 3 - Quality Checks
def test_indicator_cache_format(redis_client):
    """Test indicator cache format in Redis"""
    print("\n🔄 Testing Redis indicator cache format...")

    # Check if any indicator keys exist
    keys = redis_client.keys("indicators:*")

    if keys:
        # Get first key and verify format
        test_key = keys[0]
        test_key_str = test_key.decode() if isinstance(test_key, bytes) else test_key

        cached_value = redis_client.get(test_key_str)
        assert cached_value is not None, f"Key exists but no value: {test_key_str}"

        # Parse JSON
        data = json.loads(cached_value)
        print(f"  ✓ {test_key_str}")
        print(f"    Timestamp: {data['timestamp']}")
        print(f"    Indicators: {list(data['indicators'].keys())}")

        assert "timestamp" in data
        assert "indicators" in data
        assert len(data["indicators"]) > 0

        # Verify TTL is set
        ttl = redis_client.ttl(test_key_str)
        print(f"    TTL: {ttl}s")
        assert 0 < ttl <= 60, f"TTL should be ~60s, got {ttl}s"
    else:
        pytest.skip("No indicator keys found (Indicator Service not running)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
