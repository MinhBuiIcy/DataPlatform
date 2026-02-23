import asyncio
import contextlib
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from core.models.market_data import Candle

logger = logging.getLogger(__name__)


class BaseTimeSeriesDB(ABC):
    """
    Abstract interface for time-series databases

    NEW (Phase 2 WebSocket Stability): Includes internal queue + worker pool
    for batched inserts to prevent WebSocket backpressure.

    Implementations:
    - ClickHouseClient (OLAP, columnar)
    - TimescaleDBClient (PostgreSQL extension)
    - InfluxDBClient (Purpose-built time-series)

    Architecture:
        StreamProcessor → enqueue_trades() → Queue → Workers → Batch → ClickHouse
                              ↓ (put_nowait, fast)
                          Non-blocking
    """

    def __init__(self):
        # Internal queue + workers
        self._queue: asyncio.Queue | None = None
        self._worker_tasks: list[asyncio.Task] = []
        self._dropped_trades = 0  # Metric: dropped trades due to queue full
        self._trade_drop_rate_window: list[float] = []  # For drop rate tracking

        # Sentinel for shutdown
        self._SENTINEL = object()

    async def connect(self) -> None:
        """
        Connect to database + start worker pool

        Subclasses should:
        1. Call super().connect() first
        2. Then do provider-specific connection
        """
        from config.settings import get_settings

        settings = get_settings()

        # Create queue
        self._queue = asyncio.Queue(maxsize=settings.DB_QUEUE_SIZE)

        # Start workers
        for i in range(settings.DB_WORKERS):
            task = asyncio.create_task(self._worker(), name=f"db-worker-{i}")
            self._worker_tasks.append(task)

        logger.info(
            f"Started {settings.DB_WORKERS} database workers "
            f"(queue size: {settings.DB_QUEUE_SIZE}, batch size: {settings.DB_BATCH_SIZE})"
        )

    def enqueue_trades(self, trades: list[dict[str, Any]]) -> int:
        """
        Enqueue trades for insertion (SYNC, NON-BLOCKING)

        Batched by workers before actual DB insert.

        Args:
            trades: List of trade dictionaries

        Returns:
            Number of trades queued (not yet inserted)
        """
        if not self._queue:
            raise RuntimeError("Database client not connected")

        if not trades:
            return 0

        try:
            # Enqueue trades (sync operation)
            self._queue.put_nowait(("trades", trades))
            return len(trades)
        except asyncio.QueueFull:
            # Track drop metrics + rate
            now = time.time()
            count = len(trades)
            self._dropped_trades += count
            self._trade_drop_rate_window.extend([now] * count)

            # Keep only last 60 seconds
            cutoff = now - 60
            self._trade_drop_rate_window = [t for t in self._trade_drop_rate_window if t > cutoff]
            drop_rate = len(self._trade_drop_rate_window) / 60  # trades dropped/sec

            # SLO: DB drops are critical - panic if > 5/sec
            if drop_rate > 5:
                logger.error(
                    f"🚨 PANIC: DB trade drop rate {drop_rate:.1f}/sec exceeds threshold! "
                    f"Total dropped: {self._dropped_trades}"
                )
            else:
                logger.warning(
                    f"DB queue full, dropping {count} trades "
                    f"(rate: {drop_rate:.1f}/sec, total: {self._dropped_trades})"
                )
            return 0

    async def _worker(self) -> None:
        """
        Background worker - batch and insert to database

        Batching strategy:
        - Collect up to batch_size items (from databases.yaml)
        - Flush on sentinel (shutdown signal)
        - No timeout polling (better performance)
        """
        from config.settings import get_settings

        settings = get_settings()
        batch_size = settings.DB_BATCH_SIZE  # From databases.yaml

        batch_trades = []

        while True:
            try:
                item = await self._queue.get()

                # Sentinel check (shutdown signal)
                if item is self._SENTINEL:
                    self._queue.task_done()
                    # Flush remaining batches before exit
                    if batch_trades:
                        await self._insert_trades_impl(batch_trades)
                    break

                msg_type, items = item

                if msg_type == "trades":
                    batch_trades.extend(items)

                self._queue.task_done()

                # Flush if batch full
                if len(batch_trades) >= batch_size:
                    await self._insert_trades_impl(batch_trades)
                    batch_trades.clear()

            except asyncio.CancelledError:
                # Flush remaining before exit
                if batch_trades:
                    await self._insert_trades_impl(batch_trades)
                break
            except Exception as e:
                logger.error(f"DB worker error: {e}", exc_info=True)

    @abstractmethod
    async def _insert_trades_impl(self, trades: list[dict[str, Any]]) -> int:
        """
        Provider-specific trades insert (ClickHouse, TimescaleDB, etc.)

        Called by worker with batched trades. Must be implemented by subclass.
        """

    async def insert_trades(self, trades: list[dict[str, Any]]) -> int:
        """
        Legacy async method for backward compatibility

        NEW: Just calls enqueue_trades() (sync, non-blocking)
        """
        return self.enqueue_trades(trades)

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
        start_time: datetime | None = None,
        end_time: datetime | None = None,
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
    async def insert_candles(
        self, candles: list[dict[str, Any]], timeframe: str = "1m"
    ) -> int:
        """
        Insert OHLCV candles directly (for backfill, bypassing materialized views)

        Args:
            candles: List of candle dictionaries with keys:
                timestamp, exchange, symbol, open, high, low, close,
                volume, quote_volume, trades_count, is_synthetic
            timeframe: Target timeframe table (1m, 5m, 1h)

        Returns:
            Number of rows inserted
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

    async def close(self) -> None:
        """
        Stop workers + flush queue

        Uses sentinel pattern for clean shutdown.
        """
        # Signal workers to stop by sending sentinel to each
        if self._queue:
            for _ in self._worker_tasks:
                await self._queue.put(self._SENTINEL)

        # Wait for workers to finish (they will flush batches on sentinel)
        for task in self._worker_tasks:
            try:
                await asyncio.wait_for(task, timeout=15.0)
            except TimeoutError:
                logger.warning("DB worker didn't finish in 15s, cancelling")
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

        self._worker_tasks.clear()

        # Log metrics
        if self._dropped_trades > 0:
            logger.warning(f"DB dropped {self._dropped_trades} trades total due to queue full")

        logger.info("✓ Database workers stopped and queue flushed")
