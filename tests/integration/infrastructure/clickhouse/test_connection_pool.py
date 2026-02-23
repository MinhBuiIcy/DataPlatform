"""
Integration test for ClickHouse connection pool (TIER 2)

Tests connection pool handles concurrent inserts without "Simultaneous queries" error.

Note: Sync Service processes sequentially by design. This test simulates edge case
where multiple workers insert concurrently (stress test).
"""

import asyncio
from datetime import UTC, datetime

import pytest

from providers.opensource.clickhouse import ClickHouseClient


@pytest.mark.integration
@pytest.mark.tier2  # 🔧 TIER 2 - Infrastructure
async def test_connection_pool_handles_concurrent_queries():
    """
    Verify connection pool handles concurrent inserts without 'Simultaneous queries' error

    Design Note:
    - Sync Service processes sequentially (one exchange/symbol at a time)
    - This test simulates edge case: multiple workers inserting concurrently
    - Validates pool design, not production use case
    """
    client = ClickHouseClient()

    try:
        await client.connect()

        # Verify pool created
        assert client._pool is not None
        pool_size = client.settings.CLICKHOUSE_POOL_SIZE
        assert client._pool.qsize() == pool_size
        print(f"\n✓ Connection pool initialized with {pool_size} connections")

        # Create test data - insert candles
        async def insert_batch(batch_id: int):
            """Insert a batch of test candles"""
            candles = [
                {
                    "timestamp": datetime(2024, 1, 1, 0, i, 0, tzinfo=UTC),
                    "exchange": "binance",
                    "symbol": f"TEST{batch_id}USDT",  # Different symbols to avoid conflicts
                    "open": 50000.0 + i,
                    "high": 50100.0 + i,
                    "low": 49900.0 + i,
                    "close": 50000.0 + i,
                    "volume": 100.0,
                    "quote_volume": 5000000.0,
                    "trades_count": 100,
                    "is_synthetic": 0,
                }
                for i in range(10)
            ]
            return await client.insert_candles(candles, timeframe="1m")

        # Run 5 concurrent batches (more than pool size)
        results = await asyncio.gather(*[insert_batch(i) for i in range(5)], return_exceptions=True)

        # All should succeed
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                pytest.fail(f"Query {i + 1} failed: {result}")

            # Should return 10 (number of candles inserted)
            assert result == 10
            print(f"✓ Query {i + 1} returned {result} candles inserted")

        # Verify no "Simultaneous queries" error
        errors = [r for r in results if isinstance(r, Exception)]
        assert len(errors) == 0, "Some queries failed with errors"

        print(f"\n✓ All {len(results)} concurrent queries succeeded")
        print("✓ No 'Simultaneous queries' errors")

        # Verify pool still has all connections
        assert client._pool.qsize() == pool_size
        print(f"✓ Pool still has {pool_size} connections")

    finally:
        await client.close()
        print("✓ Connection pool closed")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
