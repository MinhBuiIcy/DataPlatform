"""
ClickHouse implementation of time-series database

Provides high-performance columnar storage for market data
"""

import logging
from typing import Any

from clickhouse_driver import Client

from config.settings import get_settings
from core.interfaces.database import BaseTimeSeriesDB

logger = logging.getLogger(__name__)


class ClickHouseClient(BaseTimeSeriesDB):
    """
    ClickHouse implementation

    Features:
    - Columnar storage (high compression)
    - Fast aggregation queries
    - Partitioning by time
    - TTL for automatic data cleanup
    """

    def __init__(self):
        self.settings = get_settings()
        self.client: Client | None = None

    async def connect(self) -> None:
        """Establish connection to ClickHouse"""
        try:
            self.client = Client(
                host=self.settings.CLICKHOUSE_HOST,
                port=self.settings.CLICKHOUSE_PORT,
                database=self.settings.CLICKHOUSE_DB,
                user=self.settings.CLICKHOUSE_USER,
                password=self.settings.CLICKHOUSE_PASSWORD,
            )
            # Test connection
            self.client.execute("SELECT 1")
            logger.info(
                f"✓ Connected to ClickHouse: "
                f"{self.settings.CLICKHOUSE_HOST}:{self.settings.CLICKHOUSE_PORT}"
            )
        except Exception as e:
            logger.error(f"✗ Failed to connect to ClickHouse: {e}")
            raise

    async def insert_trades(self, trades: list[dict[str, Any]]) -> int:
        """
        Batch insert trades into market_trades table

        Args:
            trades: List of trade dictionaries

        Returns:
            Number of rows inserted
        """
        if not trades:
            return 0

        if not self.client:
            raise RuntimeError("ClickHouse client not connected")

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

            self.client.execute(query, rows)
            logger.debug(f"Inserted {len(rows)} trades into ClickHouse")
            return len(rows)

        except Exception as e:
            logger.error(f"✗ ClickHouse insert error: {e}")
            raise

    async def query(self, sql: str, params: dict | None = None) -> list[dict]:
        """
        Execute raw SQL query

        Args:
            sql: SQL query string
            params: Query parameters

        Returns:
            List of result rows as dictionaries
        """
        if not self.client:
            raise RuntimeError("ClickHouse client not connected")

        try:
            # Only pass params if provided to avoid string formatting issues
            if params:
                result = self.client.execute(sql, params, with_column_types=True)
            else:
                result = self.client.execute(sql, with_column_types=True)

            # Convert to list of dicts
            if result and len(result) == 2:
                columns = [col[0] for col in result[1]]
                return [dict(zip(columns, row)) for row in result[0]]

            return []

        except Exception as e:
            logger.error(f"✗ ClickHouse query error: {e}")
            raise

    async def insert_orderbooks(self, orderbooks: list[dict[str, Any]]) -> int:
        """
        Batch insert order book snapshots

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

        if not self.client:
            raise RuntimeError("ClickHouse client not connected")

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

            self.client.execute(query, rows)
            logger.debug(f"Inserted {len(rows)} order book snapshots into ClickHouse")
            return len(rows)

        except Exception as e:
            logger.error(f"✗ ClickHouse orderbook insert error: {e}")
            raise

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
        Query candles from ClickHouse

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

        if not self.client:
            raise RuntimeError("ClickHouse client not connected")

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
                  AND timestamp < now()  -- Only closed candles
                ORDER BY timestamp DESC
                LIMIT %(limit)s
            """

            params = {"exchange": exchange, "symbol": symbol, "limit": limit}

            result = self.client.execute(query, params)

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
            logger.error(f"✗ ClickHouse query_candles error: {e}")
            raise

    async def insert_indicators(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        timestamp: Any,
        indicators: dict[str, float],
    ) -> int:
        """
        Insert indicator values into indicators table

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

        if not self.client:
            raise RuntimeError("ClickHouse client not connected")

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

            self.client.execute(query, rows)
            logger.debug(f"Inserted {len(rows)} indicators for {exchange}/{symbol}/{timeframe}")
            return len(rows)

        except Exception as e:
            logger.error(f"✗ ClickHouse insert_indicators error: {e}")
            raise

    async def close(self) -> None:
        """Close connection"""
        if self.client:
            self.client.disconnect()
            logger.info("✓ ClickHouse connection closed")
