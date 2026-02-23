"""
Unit tests for ClickHouse connection pooling

Tests:
- Connection pool creation
- Pool size configuration
- Poison connection recovery
- Connection reuse
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from providers.opensource.clickhouse import ClickHouseClient


@pytest.mark.unit
async def test_connection_pool_creation():
    """Verify connection pool initialized with correct size"""
    with patch("providers.opensource.clickhouse.Client") as mock_client_class:
        # Mock the Client class to return mock instances
        mock_conn = MagicMock()
        mock_conn.execute = MagicMock(return_value=[[1]])
        mock_client_class.return_value = mock_conn

        # Mock settings to return pool size = 3
        with patch("providers.opensource.clickhouse.get_settings") as mock_settings:
            mock_settings.return_value.CLICKHOUSE_POOL_SIZE = 3
            mock_settings.return_value.CLICKHOUSE_HOST = "clickhouse"
            mock_settings.return_value.CLICKHOUSE_PORT = 9000
            mock_settings.return_value.CLICKHOUSE_DB = "trading"
            mock_settings.return_value.CLICKHOUSE_USER = "trading_user"
            mock_settings.return_value.CLICKHOUSE_PASSWORD = "trading_pass"

            client = ClickHouseClient()

            await client.connect()

            # Verify 3 connections created
            assert mock_client_class.call_count == 3
            assert client._pool.qsize() == 3

            await client.close()


@pytest.mark.unit
async def test_pool_size_from_config():
    """Verify pool size read from config"""
    from config.settings import get_settings

    settings = get_settings()
    pool_size = settings.CLICKHOUSE_POOL_SIZE

    assert pool_size >= 1
    assert isinstance(pool_size, int)
    # Default should be same as DB_WORKERS
    assert pool_size == settings.DB_WORKERS or pool_size == 3


@pytest.mark.unit
async def test_poison_connection_recovery():
    """Verify poisoned connection is replaced, not returned"""
    with patch("providers.opensource.clickhouse.Client") as mock_client_class:
        # Create mock connections
        poisoned_conn = MagicMock()
        poisoned_conn.execute = MagicMock(side_effect=Exception("Connection lost"))
        poisoned_conn.disconnect = MagicMock()

        new_conn = MagicMock()
        new_conn.execute = MagicMock(return_value=[[1]])

        # First 1 call for pool creation, then poisoned replacement
        mock_client_class.side_effect = [
            MagicMock(execute=MagicMock(return_value=[[1]])),  # Pool conn 1
            new_conn,  # Replacement conn
        ]

        with patch("providers.opensource.clickhouse.get_settings") as mock_settings:
            mock_settings.return_value.CLICKHOUSE_POOL_SIZE = 1  # Single connection pool
            mock_settings.return_value.CLICKHOUSE_HOST = "clickhouse"
            mock_settings.return_value.CLICKHOUSE_PORT = 9000
            mock_settings.return_value.CLICKHOUSE_DB = "trading"
            mock_settings.return_value.CLICKHOUSE_USER = "trading_user"
            mock_settings.return_value.CLICKHOUSE_PASSWORD = "trading_pass"

            client = ClickHouseClient()
            await client.connect()

            # Drain pool and inject poisoned connection (FIFO queue)
            await client._pool.get()  # Remove the good connection
            await client._pool.put(poisoned_conn)  # Add poisoned one

            # Try to insert with poisoned connection
            trades = [
                {
                    "timestamp": "2024-01-01 00:00:00",
                    "exchange": "binance",
                    "symbol": "BTCUSDT",
                    "trade_id": "test_123",
                    "price": 50000.0,
                    "quantity": 1.0,
                    "side": "buy",
                    "is_buyer_maker": False,
                }
            ]

            result = await client._insert_trades_impl(trades)

            # Should return 0 (failed due to poisoned connection)
            assert result == 0
            # Pool should still have 1 connection (new one replaced poisoned)
            assert client._pool.qsize() == 1
            # Verify poisoned connection was disconnected
            poisoned_conn.disconnect.assert_called_once()

            await client.close()


@pytest.mark.unit
async def test_concurrent_inserts_with_pool():
    """Verify pool handles concurrent operations correctly"""
    with patch("providers.opensource.clickhouse.Client") as mock_client_class:
        # Mock connection that tracks INSERT queries only
        call_count = {"value": 0}

        def mock_execute(query, *args, **kwargs):
            # Count only INSERT queries, not SELECT 1 for connection test
            if isinstance(query, str) and "INSERT" in query:
                call_count["value"] += 1
            return [[1]]

        mock_conn = MagicMock()
        mock_conn.execute = MagicMock(side_effect=mock_execute)

        # Return same mock for all connections (for simplicity)
        mock_client_class.return_value = mock_conn

        with patch("providers.opensource.clickhouse.get_settings") as mock_settings:
            mock_settings.return_value.CLICKHOUSE_POOL_SIZE = 2  # Small pool
            mock_settings.return_value.CLICKHOUSE_HOST = "clickhouse"
            mock_settings.return_value.CLICKHOUSE_PORT = 9000
            mock_settings.return_value.CLICKHOUSE_DB = "trading"
            mock_settings.return_value.CLICKHOUSE_USER = "trading_user"
            mock_settings.return_value.CLICKHOUSE_PASSWORD = "trading_pass"

            client = ClickHouseClient()
            await client.connect()

            # Create multiple concurrent insert tasks
            async def insert_batch(batch_id: int):
                trades = [
                    {
                        "timestamp": "2024-01-01 00:00:00",
                        "exchange": "binance",
                        "symbol": "BTCUSDT",
                        "trade_id": f"test_{batch_id}_{i}",
                        "price": 50000.0 + i,
                        "quantity": 1.0,
                        "side": "buy",
                        "is_buyer_maker": False,
                    }
                    for i in range(5)
                ]
                return await client._insert_trades_impl(trades)

            # Run 4 concurrent batches (more than pool size)
            results = await asyncio.gather(*[insert_batch(i) for i in range(4)])

            # All should succeed
            for result in results:
                assert result == 5  # 5 trades per batch

            # Should have executed 4 INSERT queries
            assert call_count["value"] == 4

            await client.close()


@pytest.mark.unit
async def test_pool_connection_reuse():
    """Verify connections are returned to pool and reused"""
    with patch("providers.opensource.clickhouse.Client") as mock_client_class:
        mock_conn = MagicMock()
        mock_conn.execute = MagicMock(return_value=[[1]])
        mock_client_class.return_value = mock_conn

        with patch("providers.opensource.clickhouse.get_settings") as mock_settings:
            mock_settings.return_value.CLICKHOUSE_POOL_SIZE = 1  # Single connection
            mock_settings.return_value.CLICKHOUSE_HOST = "clickhouse"
            mock_settings.return_value.CLICKHOUSE_PORT = 9000
            mock_settings.return_value.CLICKHOUSE_DB = "trading"
            mock_settings.return_value.CLICKHOUSE_USER = "trading_user"
            mock_settings.return_value.CLICKHOUSE_PASSWORD = "trading_pass"

            client = ClickHouseClient()
            await client.connect()

            # Pool should have 1 connection
            assert client._pool.qsize() == 1

            # Use connection for insert
            trades = [
                {
                    "timestamp": "2024-01-01 00:00:00",
                    "exchange": "binance",
                    "symbol": "BTCUSDT",
                    "trade_id": "test_1",
                    "price": 50000.0,
                    "quantity": 1.0,
                    "side": "buy",
                    "is_buyer_maker": False,
                }
            ]
            await client._insert_trades_impl(trades)

            # Connection should be returned to pool
            assert client._pool.qsize() == 1

            # Use again
            await client._insert_trades_impl(trades)

            # Still have 1 connection
            assert client._pool.qsize() == 1

            await client.close()


@pytest.mark.unit
async def test_pool_closes_all_connections():
    """Verify close() drains and closes all pooled connections"""
    with patch("providers.opensource.clickhouse.Client") as mock_client_class:
        mock_conns = []
        for _ in range(3):
            conn = MagicMock()
            conn.execute = MagicMock(return_value=[[1]])
            conn.disconnect = MagicMock()
            mock_conns.append(conn)

        mock_client_class.side_effect = mock_conns

        with patch("providers.opensource.clickhouse.get_settings") as mock_settings:
            mock_settings.return_value.CLICKHOUSE_POOL_SIZE = 3
            mock_settings.return_value.CLICKHOUSE_HOST = "clickhouse"
            mock_settings.return_value.CLICKHOUSE_PORT = 9000
            mock_settings.return_value.CLICKHOUSE_DB = "trading"
            mock_settings.return_value.CLICKHOUSE_USER = "trading_user"
            mock_settings.return_value.CLICKHOUSE_PASSWORD = "trading_pass"

            client = ClickHouseClient()
            await client.connect()

            # Close client
            await client.close()

            # Verify all connections were disconnected
            for conn in mock_conns:
                conn.disconnect.assert_called_once()

            # Pool should be empty
            assert client._pool.empty()
