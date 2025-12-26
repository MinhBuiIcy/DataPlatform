from abc import ABC, abstractmethod
from typing import Any


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
    async def close(self) -> None:
        """Close connection"""
