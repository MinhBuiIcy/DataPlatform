"""
Integration test for ClickHouse basic connectivity (TIER 2)

Verifies ClickHouse client connects successfully.
"""

import pytest

from providers.opensource.clickhouse import ClickHouseClient


@pytest.mark.integration
@pytest.mark.tier2  # 🔧 TIER 2 - Infrastructure
async def test_clickhouse_basic_connectivity():
    """Verify ClickHouse client connects successfully"""
    client = ClickHouseClient()
    await client.connect()

    try:
        # Simple query to verify connection
        result = await client.query("SELECT 1")
        assert len(result) == 1
        assert result[0].get("1") == 1
        print("\n✓ ClickHouse client connected successfully")
    finally:
        await client.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
