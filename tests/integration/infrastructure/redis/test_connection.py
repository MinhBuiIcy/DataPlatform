"""
Integration test for Redis basic connectivity (TIER 2)

Verifies Redis client connects successfully.
"""

import pytest
from providers.opensource.redis_client import RedisClient


@pytest.mark.integration
@pytest.mark.tier2  # 🔧 TIER 2 - Infrastructure
async def test_redis_basic_connectivity():
    """Verify Redis client connects successfully"""
    client = RedisClient()
    await client.connect()

    try:
        # Simple ping to verify connection
        await client.client.ping()
        print("\n✓ Redis client connected successfully")
    finally:
        await client.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
