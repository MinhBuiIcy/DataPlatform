"""
ClickHouse implementation of time-series database

Provides high-performance columnar storage for market data

Note: clickhouse_driver.Client is synchronous. All execute() calls are
wrapped in asyncio.to_thread() to avoid blocking the event loop.
"""

import asyncio
import contextlib
import logging
from typing import Any

from clickhouse_driver import Client

from config.settings import get_settings
from core.interfaces.database import BaseTimeSeriesDB

logger = logging.getLogger(__name__)


class ClickHouseClient(BaseTimeSeriesDB):
    """
    ClickHouse implementation with connection pooling + worker pool

    Architecture:
        StreamProcessor → enqueue_trades() → Queue → Workers → Pool → ClickHouse
                              ↓ (put_nowait, fast)       ↓ (get connection)
                          Non-blocking              Connection pool

    Features:
    - Internal queue (2000 items) + worker pool (3 workers)
    - Connection pool (configurable, default: same as workers)
    - Auto-batching (100 trades per insert)
    - Columnar storage (high compression)
    - Fast aggregation queries
    - Partitioning by time
    - TTL for automatic data cleanup

    Connection Pooling:
    - Each worker gets a connection from pool (blocks if all busy)
    - Poisoned connections are replaced automatically
    - Pool size configurable via databases.yaml (clickhouse.pool_size)
    """

    def __init__(self):
        super().__init__()  # Initialize queue + workers from BaseTimeSeriesDB
        self.settings = get_settings()
        self._pool: asyncio.Queue[Client] | None = None

    async def connect(self) -> None:
        """Connect to ClickHouse + start worker pool"""
        # 1. Start workers FIRST (BaseTimeSeriesDB.connect())
        await super().connect()

        # 2. Create connection pool
        pool_size = self.settings.CLICKHOUSE_POOL_SIZE
        self._pool = asyncio.Queue(maxsize=pool_size)

        logger.info(
            f"Creating ClickHouse connection pool "
            f"(size={pool_size}, host={self.settings.CLICKHOUSE_HOST}:{self.settings.CLICKHOUSE_PORT})..."
        )

        for i in range(pool_size):
            try:
                conn = await self._create_connection()
                await self._pool.put(conn)
                logger.debug(f"  ✓ Connection {i + 1}/{pool_size} added to pool")
            except Exception as e:
                logger.error(f"Failed to create connection {i + 1}: {e}")
                raise

        logger.info(f"✓ ClickHouse pool ready with {pool_size} connections")

    async def _create_connection(self) -> Client:
        """
        Factory method: create a new ClickHouse connection.

        Called during:
        - Initial pool creation (connect())
        - Poison connection recovery (all insert/query methods)

        Returns:
            Connected ClickHouse Client

        Raises:
            Exception if connection fails
        """
        conn = Client(
            host=self.settings.CLICKHOUSE_HOST,
            port=self.settings.CLICKHOUSE_PORT,
            database=self.settings.CLICKHOUSE_DB,
            user=self.settings.CLICKHOUSE_USER,
            password=self.settings.CLICKHOUSE_PASSWORD,
        )

        # Test connection with simple query
        await asyncio.to_thread(conn.execute, "SELECT 1")

        return conn

    async def _insert_trades_impl(self, trades: list[dict[str, Any]]) -> int:
        """
        ClickHouse batch insert with connection pooling.

        Flow:
        1. Get connection from pool (blocks if pool empty)
        2. Execute query
        3. If success: return connection to pool
        4. If error (poisoned):
           - Disconnect broken connection
           - Try to create new connection
           - If recreate succeeds: return new connection to pool
           - If recreate fails: DO NOT return broken conn, log critical error

        Args:
            trades: Batched trade data (from BaseTimeSeriesDB worker)

        Returns:
            Number of rows inserted (0 if failed)
        """
        if not trades:
            return 0

        if not self._pool:
            raise RuntimeError("ClickHouse pool not initialized")

        # Get connection from pool (blocks if all connections busy)
        conn = await self._pool.get()
        poisoned = False

        try:
            # Convert to format expected by ClickHouse
            rows = [
                (
                    trade["timestamp"],
                    trade["exchange"],
                    trade["symbol"],
                    trade["trade_id"],
                    float(trade["price"]),
                    float(trade["quantity"]),
                    trade["side"],
                    1 if trade["is_buyer_maker"] else 0,
                )
                for trade in trades
            ]

            query = """
                INSERT INTO trading.market_trades
                (timestamp, exchange, symbol, trade_id, price, quantity, side, is_buyer_maker)
                VALUES
            """

            # Execute in thread pool (sync driver)
            await asyncio.to_thread(conn.execute, query, rows)

            logger.debug(f"Inserted {len(rows)} trades into ClickHouse")
            return len(rows)

        except Exception as e:
            # Connection is poisoned
            poisoned = True
            logger.error(f"✗ ClickHouse insert error: {e}")
            return 0

        finally:
            if poisoned:
                # Attempt to recover from poison
                with contextlib.suppress(Exception):
                    conn.disconnect()

                try:
                    # Try to create a new connection
                    conn = await self._create_connection()
                    logger.warning("Replaced poisoned connection with new one")

                except Exception as e:
                    # Failed to recreate connection
                    logger.critical(
                        f"Failed to recreate ClickHouse connection: {e}. "
                        f"Pool size reduced by 1 (was {self.settings.CLICKHOUSE_POOL_SIZE})"
                    )
                    # DO NOT put broken conn back to pool
                    # Just return - pool size permanently reduced by 1
                    # Operator must restart service to restore full pool
                    return 0

            # Return connection to pool (either original or recreated)
            await self._pool.put(conn)

    async def query(self, sql: str, params: dict | None = None) -> list[dict]:
        """
        Execute raw SQL query with connection pooling

        Args:
            sql: SQL query string
            params: Query parameters

        Returns:
            List of result rows as dictionaries
        """
        if not self._pool:
            raise RuntimeError("ClickHouse pool not initialized")

        # Get connection from pool
        conn = await self._pool.get()
        poisoned = False

        try:
            # Only pass params if provided to avoid string formatting issues
            if params:
                result = await asyncio.to_thread(conn.execute, sql, params, with_column_types=True)
            else:
                result = await asyncio.to_thread(conn.execute, sql, with_column_types=True)

            # Convert to list of dicts
            if result and len(result) == 2:
                columns = [col[0] for col in result[1]]
                return [dict(zip(columns, row)) for row in result[0]]

            return []

        except Exception as e:
            poisoned = True
            logger.error(f"✗ ClickHouse query error: {e}")
            raise

        finally:
            if poisoned:
                with contextlib.suppress(Exception):
                    conn.disconnect()
                try:
                    conn = await self._create_connection()
                    logger.warning("Replaced poisoned connection")
                except Exception as e:
                    logger.critical(f"Failed to recreate connection: {e}")
                    raise  # Query methods should raise on connection failure

            await self._pool.put(conn)

    async def insert_orderbooks(self, orderbooks: list[dict[str, Any]]) -> int:
        """
        Batch insert order book snapshots with connection pooling

        Args:
            orderbooks: List of order book dicts from OrderBook.to_dict()

        Returns:
            Number of rows inserted

        Example:
            >>> orderbooks = [ob1.to_dict(), ob2.to_dict()]
            >>> count = await clickhouse.insert_orderbooks(orderbooks)
            >>> print(f"Inserted {count} order books")
        """
        if not orderbooks:
            return 0

        if not self._pool:
            raise RuntimeError("ClickHouse pool not initialized")

        conn = await self._pool.get()
        poisoned = False

        try:
            # Convert to format expected by ClickHouse
            rows = [
                (
                    ob["timestamp"],
                    ob["exchange"],
                    ob["symbol"],
                    [(float(p), float(q)) for p, q in ob["bids"]],  # Array(Tuple(Float64, Float64))
                    [(float(p), float(q)) for p, q in ob["asks"]],
                    ob.get("checksum", 0),
                )
                for ob in orderbooks
            ]

            query = """
                INSERT INTO trading.orderbook_snapshots
                (timestamp, exchange, symbol, bids, asks, checksum)
                VALUES
            """

            await asyncio.to_thread(conn.execute, query, rows)
            logger.debug(f"Inserted {len(rows)} order book snapshots into ClickHouse")
            return len(rows)

        except Exception as e:
            poisoned = True
            logger.error(f"✗ ClickHouse orderbook insert error: {e}")
            raise

        finally:
            if poisoned:
                with contextlib.suppress(Exception):
                    conn.disconnect()
                try:
                    conn = await self._create_connection()
                    logger.warning("Replaced poisoned connection")
                except Exception as e:
                    logger.critical(f"Failed to recreate connection: {e}")
                    raise

            await self._pool.put(conn)

    async def insert_candles(self, candles: list[dict[str, Any]], timeframe: str = "1m") -> int:
        """
        Batch insert candles with connection pooling (for backfill, bypassing materialized views)

        Args:
            candles: List of candle dictionaries
            timeframe: Target timeframe table (1m, 5m, 1h)

        Returns:
            Number of rows inserted
        """
        if not candles:
            return 0

        if not self._pool:
            raise RuntimeError("ClickHouse pool not initialized")

        conn = await self._pool.get()
        poisoned = False

        try:
            # Map timeframe to table name
            table_mapping = {"1m": "candles_1m", "5m": "candles_5m", "1h": "candles_1h"}
            table = table_mapping.get(timeframe)
            if not table:
                raise ValueError(f"Unsupported timeframe for insert: {timeframe}")

            rows = [
                (
                    candle["timestamp"],
                    candle["exchange"],
                    candle["symbol"],
                    float(candle["open"]),
                    float(candle["high"]),
                    float(candle["low"]),
                    float(candle["close"]),
                    float(candle["volume"]),
                    float(candle.get("quote_volume", 0)),
                    int(candle.get("trades_count", 0)),
                    int(candle.get("is_synthetic", 0)),
                )
                for candle in candles
            ]

            query = f"""
                INSERT INTO trading.{table}
                (timestamp, exchange, symbol, open, high, low, close,
                 volume, quote_volume, trades_count, is_synthetic)
                VALUES
            """

            await asyncio.to_thread(conn.execute, query, rows)
            logger.debug(f"Inserted {len(rows)} candles into trading.{table}")
            return len(rows)

        except Exception as e:
            poisoned = True
            logger.error(f"✗ ClickHouse insert_candles error: {e}")
            raise

        finally:
            if poisoned:
                with contextlib.suppress(Exception):
                    conn.disconnect()
                try:
                    conn = await self._create_connection()
                    logger.warning("Replaced poisoned connection")
                except Exception as e:
                    logger.critical(f"Failed to recreate connection: {e}")
                    raise

            await self._pool.put(conn)

    async def query_candles(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        limit: int = 200,
        start_time: Any | None = None,
        end_time: Any | None = None,
    ) -> list:
        """
        Query candles from ClickHouse with connection pooling

        Args:
            exchange: Exchange name
            symbol: Trading pair
            timeframe: Timeframe (1m, 5m, 1h, etc.)
            limit: Max candles to return
            start_time: Start time filter (optional)
            end_time: End time filter (optional)

        Returns:
            List of Candle objects (may have gaps)
        """
        from core.models.market_data import Candle

        if not self._pool:
            raise RuntimeError("ClickHouse pool not initialized")

        conn = await self._pool.get()
        poisoned = False

        try:
            # Map timeframe to table name
            table_mapping = {"1m": "candles_1m", "5m": "candles_5m", "1h": "candles_1h"}
            table = table_mapping.get(timeframe, "candles_1m")

            # Build query
            query = f"""
                SELECT
                    timestamp, exchange, symbol, '{timeframe}' as timeframe,
                    open, high, low, close,
                    volume, quote_volume, trades_count, is_synthetic
                FROM trading.{table}
                WHERE exchange = %(exchange)s
                  AND symbol = %(symbol)s
                  AND timestamp < toStartOfMinute(now())  -- Only closed candles (exclude current minute)
                ORDER BY timestamp DESC
                LIMIT %(limit)s
            """

            params = {"exchange": exchange, "symbol": symbol, "limit": limit}

            result = await asyncio.to_thread(conn.execute, query, params)

            # Convert to Candle objects (reverse to get ASC order)
            candles = []
            for row in reversed(result):
                candles.append(
                    Candle(
                        timestamp=row[0],
                        exchange=row[1],
                        symbol=row[2],
                        timeframe=row[3],
                        open=row[4],
                        high=row[5],
                        low=row[6],
                        close=row[7],
                        volume=row[8],
                        quote_volume=row[9],
                        trades_count=row[10],
                        is_synthetic=bool(row[11]),
                    )
                )

            logger.debug(f"Queried {len(candles)} candles for {exchange}/{symbol}/{timeframe}")
            return candles

        except Exception as e:
            poisoned = True
            logger.error(f"✗ ClickHouse query_candles error: {e}")
            raise

        finally:
            if poisoned:
                with contextlib.suppress(Exception):
                    conn.disconnect()
                try:
                    conn = await self._create_connection()
                    logger.warning("Replaced poisoned connection")
                except Exception as e:
                    logger.critical(f"Failed to recreate connection: {e}")
                    raise

            await self._pool.put(conn)

    async def insert_indicators(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        timestamp: Any,
        indicators: dict[str, float],
    ) -> int:
        """
        Insert indicator values with connection pooling

        Uses ReplacingMergeTree for automatic deduplication
        ORDER BY (exchange, symbol, timeframe, indicator_name, timestamp)

        Args:
            exchange: Exchange name
            symbol: Trading pair
            timeframe: Timeframe
            timestamp: Candle timestamp
            indicators: Dict of indicator values

        Returns:
            Number of rows inserted
        """
        if not indicators:
            return 0

        if not self._pool:
            raise RuntimeError("ClickHouse pool not initialized")

        conn = await self._pool.get()
        poisoned = False

        try:
            # Convert to rows format
            rows = [
                (timestamp, exchange, symbol, timeframe, indicator_name, float(value))
                for indicator_name, value in indicators.items()
            ]

            query = """
                INSERT INTO trading.indicators
                (timestamp, exchange, symbol, timeframe, indicator_name, indicator_value)
                VALUES
            """

            await asyncio.to_thread(conn.execute, query, rows)
            logger.debug(f"Inserted {len(rows)} indicators for {exchange}/{symbol}/{timeframe}")
            return len(rows)

        except Exception as e:
            poisoned = True
            logger.error(f"✗ ClickHouse insert_indicators error: {e}")
            raise

        finally:
            if poisoned:
                with contextlib.suppress(Exception):
                    conn.disconnect()
                try:
                    conn = await self._create_connection()
                    logger.warning("Replaced poisoned connection")
                except Exception as e:
                    logger.critical(f"Failed to recreate connection: {e}")
                    raise

            await self._pool.put(conn)

    async def close(self) -> None:
        """Stop workers + close all pooled ClickHouse connections"""
        # 1. Stop workers first (will flush queue) - BaseTimeSeriesDB.close()
        await super().close()

        # 2. Close all connections in pool
        if self._pool:
            logger.info("Closing ClickHouse connection pool...")
            closed_count = 0

            while not self._pool.empty():
                try:
                    conn = await asyncio.wait_for(self._pool.get(), timeout=1.0)
                    conn.disconnect()
                    closed_count += 1
                except TimeoutError:
                    break
                except Exception as e:
                    logger.warning(f"Error closing connection: {e}")

            logger.info(f"✓ Closed {closed_count} ClickHouse connections")
