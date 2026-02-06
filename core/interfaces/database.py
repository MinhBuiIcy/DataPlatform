from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional

from core.models.market_data import Candle


class BaseTimeSeriesDB(ABC):
    """
    Abstract interface for time-series databases

    Implementations:
    - ClickHouseClient (OLAP, columnar)
    - TimescaleDBClient (PostgreSQL extension)
    - InfluxDBClient (Purpose-built time-series)
    """

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to database"""

    @abstractmethod
    async def insert_trades(self, trades: list[dict[str, Any]]) -> int:
        """
        Insert market trades in batch

        Args:
            trades: List of trade dictionaries

        Returns:
            Number of rows inserted
        """

    @abstractmethod
    async def query(self, sql: str, params: dict | None = None) -> list[dict]:
        """
        Execute raw SQL query

        Args:
            sql: SQL query string
            params: Query parameters

        Returns:
            List of result rows as dictionaries
        """

    @abstractmethod
    async def query_candles(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        limit: int = 200,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> list[Candle]:
        """
        Query candles from database (pure query, no gap filling)

        Args:
            exchange: Exchange name (binance, coinbase, kraken)
            symbol: Trading pair (BTC/USDT)
            timeframe: Timeframe (1m, 5m, 15m, 1h, 4h, 1d)
            limit: Maximum number of candles to return
            start_time: Start time filter (optional)
            end_time: End time filter (optional)

        Returns:
            List of candles (may have gaps)

        Note:
            Use core.utils.gap_handling.detect_gaps() and fill_gaps()
            if you need complete time series
        """

    @abstractmethod
    async def insert_indicators(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        timestamp: datetime,
        indicators: dict[str, float],
    ) -> int:
        """
        Insert indicator values in batch

        Args:
            exchange: Exchange name (binance, coinbase, kraken)
            symbol: Trading pair (BTCUSDT, BTC-USD, etc.)
            timeframe: Timeframe (1m, 5m, 1h, etc.)
            timestamp: Candle timestamp
            indicators: Dict of indicator values {"SMA_20": 45000.5, "RSI_14": 65.2, ...}

        Returns:
            Number of rows inserted

        Note:
            Uses ReplacingMergeTree for deduplication
            ORDER BY (exchange, symbol, timeframe, indicator_name, timestamp)
        """

    @abstractmethod
    async def close(self) -> None:
        """Close connection"""
