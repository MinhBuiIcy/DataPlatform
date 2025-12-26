"""
Stream processor - Distribute trades and order books to multiple destinations

Sends data to:
1. Streaming (Kafka/Kinesis for downstream processing)
2. Storage (S3/GCS/Azure Blob - raw data backup)
3. TimeSeriesDB (ClickHouse/TimescaleDB - real-time analytics)
4. Cache (Redis/Memcached - latest price cache)
"""

import json
import logging
from datetime import timedelta

from config.settings import get_settings
from core.models.market_data import OrderBook, Trade
from core.validators.market_data import DataValidator
from factory.client_factory import (
    create_cache_client,
    create_storage_client,
    create_stream_client,
    create_timeseries_db,
)

logger = logging.getLogger(__name__)


class StreamProcessor:
    """
    Process trades and order books - distribute to multiple destinations

    Architecture (Cloud-agnostic via BaseClient interfaces):
    - Streaming (Kafka/Kinesis): Fire-and-forget streaming
    - Storage (S3/GCS/Azure Blob): Raw data backup (data lake pattern)
    - TimeSeriesDB (ClickHouse/TimescaleDB): Batch insert (100 trades, 50 order books)
    - Cache (Redis/Memcached): Latest price cache + order book cache
    """

    def __init__(self, buffer_size: int = 100):
        """
        Initialize stream processor

        Args:
            buffer_size: Number of trades to buffer before ClickHouse insert
        """
        self.settings = get_settings()

        # Create clients via factory (dependency injection)
        self.stream_client = create_stream_client()
        self.storage_client = create_storage_client()
        self.timeseries_db = create_timeseries_db()
        self.cache_client = create_cache_client()

        # Batch buffers for ClickHouse
        self.trade_buffer = []
        self.orderbook_buffer = []
        self.buffer_size = buffer_size
        self.orderbook_buffer_size = 50  # Smaller buffer for order books (higher frequency)

        # Track last order book backup per symbol (for sampling)
        self._last_orderbook_backup = {}

        # Data quality validator
        self.validator = DataValidator(spike_threshold_pct=10.0)

    async def connect(self) -> None:
        """Initialize all clients"""
        await self.stream_client.connect()
        await self.storage_client.connect()
        await self.timeseries_db.connect()
        await self.cache_client.connect()
        logger.info("✓ All downstream clients connected (Stream, Storage, TimeSeriesDB, Cache)")

    async def process_trade(self, trade: Trade) -> None:
        """
        Process single trade - distribute to 4 destinations

        Flow:
        0. Validate data quality
        1. Send to stream (Kafka/Kinesis - async, don't wait)
        2. Backup to storage (raw data lake)
        3. Buffer for timeseries DB (batch insert)
        4. Update cache (latest price)

        Args:
            trade: Trade object from WebSocket
        """

        # 0. Validate before processing
        is_valid, error = self.validator.validate_trade(trade)
        if not is_valid:
            logger.error(f"❌ Invalid trade rejected: {error} - {trade.symbol} @ {trade.price}")
            return  # Skip invalid data

        # 1. Send to stream (fire-and-forget)
        await self._send_to_stream(trade)

        # 2. Backup to storage (raw data)
        await self._backup_to_storage(trade)

        # 3. Buffer for timeseries DB
        self.trade_buffer.append(trade.to_dict())
        if len(self.trade_buffer) >= self.buffer_size:
            await self._flush_to_timeseries_db()

        # 4. Update cache
        await self._update_cache(trade)

    async def _send_to_stream(self, trade: Trade) -> None:
        """
        Send trade to streaming platform (Kafka topic or Kinesis stream)

        Purpose:
        - Downstream processing (Lambda, Spark, Flink)
        - Event sourcing
        - Real-time stream analytics

        Args:
            trade: Trade object
        """
        try:
            await self.stream_client.send_record(
                stream_name=self.settings.STREAM_MARKET_TRADES,
                data=trade.to_dict(),
                partition_key=trade.symbol,  # Same symbol → same partition/shard (ordering)
            )
        except Exception as e:
            logger.error(f"✗ Stream send error: {e}")
            # Don't raise - continue to other destinations

    async def _backup_to_storage(self, trade: Trade) -> None:
        """
        Backup raw trade data to object storage (S3/GCS/Azure Blob)

        Purpose:
        - Long-term storage (data lake pattern)
        - Replay/reprocessing capability
        - Audit trail & compliance
        - ML training data

        Storage Structure:
        bucket://trading-raw-data-local/trades/
            {year}/{month}/{day}/
                {exchange}-{symbol}-{timestamp}-{trade_id}.json

        Example:
        s3://trading-raw-data-local/trades/2025/12/23/
            binance-BTCUSDT-20251223-193045-123456.json

        Args:
            trade: Trade object
        """
        try:
            # Generate key with partitioning by date
            timestamp = trade.timestamp
            year = timestamp.strftime("%Y")
            month = timestamp.strftime("%m")
            day = timestamp.strftime("%d")

            # Filename: {exchange}-{symbol}-{timestamp}-{trade_id}.json
            filename = (
                f"{trade.exchange}-{trade.symbol}-"
                f"{timestamp.strftime('%Y%m%d-%H%M%S')}-{trade.trade_id}.json"
            )

            storage_key = f"trades/{year}/{month}/{day}/{filename}"

            # Convert trade to JSON
            trade_json = json.dumps(trade.to_dict(), default=str)

            # Upload to storage
            await self.storage_client.upload_file(
                bucket=self.settings.S3_BUCKET_RAW_DATA,
                key=storage_key,
                data=trade_json.encode("utf-8"),
            )

        except Exception as e:
            logger.error(f"✗ Storage backup error: {e}")
            # Don't raise - storage backup is not critical for real-time flow

    async def _flush_to_timeseries_db(self) -> None:
        """
        Batch insert trades to timeseries database (ClickHouse/TimescaleDB)

        Why batch?
        - 1 insert per trade: ~10ms each → 100 trades = 1000ms
        - 100 trades in 1 insert: ~50ms total → 20x faster!
        """
        if not self.trade_buffer:
            return

        try:
            count = await self.timeseries_db.insert_trades(self.trade_buffer)
            logger.info(f"✓ Inserted {count} trades to timeseries DB")
            self.trade_buffer.clear()
        except Exception as e:
            logger.error(f"✗ Timeseries DB insert error: {e}")
            # Keep buffer for retry
            # TODO: Implement retry with exponential backoff in Phase 6

    async def _update_cache(self, trade: Trade) -> None:
        """
        Update latest price in cache (Redis/Memcached)

        Purpose:
        - Fast API response (GET /latest-price/BTCUSDT)
        - Dashboard current price
        - Strategy execution (check current price)

        Cache structure:
        Key: "latest_price:binance:BTCUSDT"
        Value: {"price": "50000.00", "timestamp": "...", "side": "buy"}

        Args:
            trade: Trade object
        """
        try:
            cache_key = f"latest_price:{trade.exchange}:{trade.symbol}"
            cache_value = json.dumps(
                {
                    "price": str(trade.price),
                    "timestamp": trade.timestamp.isoformat(),
                    "side": trade.side,
                    "quantity": str(trade.quantity),
                }
            )
            await self.cache_client.set(cache_key, cache_value)
        except Exception as e:
            logger.error(f"✗ Cache error: {e}")
            # Don't raise - not critical

    async def process_orderbook(self, orderbook: OrderBook) -> None:
        """
        Process order book snapshot - distribute to 4 destinations

        Flow:
        0. Validate data quality
        1. Send to stream (Kafka/Kinesis - async, don't wait)
        2. Sample & backup to storage (1 snapshot per second to save space)
        3. Buffer for timeseries DB (batch insert)
        4. Update cache (latest order book)

        Args:
            orderbook: OrderBook object from WebSocket
        """

        # 0. Validate before processing
        is_valid, error = self.validator.validate_orderbook(orderbook)
        if not is_valid:
            logger.error(f"❌ Invalid order book rejected: {error} - {orderbook.symbol}")
            return  # Skip invalid data

        # 1. Send to stream (fire-and-forget)
        await self._send_orderbook_to_stream(orderbook)

        # 2. Sample & backup to storage (avoid storing every 100ms update)
        if self._should_backup_orderbook(orderbook):
            await self._backup_orderbook_to_storage(orderbook)

        # 3. Buffer for timeseries DB
        self.orderbook_buffer.append(orderbook.to_dict())
        if len(self.orderbook_buffer) >= self.orderbook_buffer_size:
            await self._flush_orderbooks_to_timeseries_db()

        # 4. Update cache (latest order book)
        await self._update_orderbook_cache(orderbook)

    async def _send_orderbook_to_stream(self, orderbook: OrderBook) -> None:
        """
        Send order book to streaming platform (Kafka topic or Kinesis stream)

        Purpose:
        - Downstream processing (Lambda, Flink)
        - Real-time analytics on order book changes
        - Spread monitoring, liquidity analysis

        Args:
            orderbook: OrderBook object
        """
        try:
            await self.stream_client.send_record(
                stream_name=self.settings.STREAM_ORDER_BOOKS,
                data=orderbook.to_dict(),
                partition_key=orderbook.symbol,  # Same symbol → same partition/shard
            )
        except Exception as e:
            logger.error(f"✗ Stream orderbook send error: {e}")
            # Don't raise - continue to other destinations

    def _should_backup_orderbook(self, orderbook: OrderBook) -> bool:
        """
        Sample order books: backup 1 per second per symbol

        Why sample?
        - Order books update every 100ms (10 updates/sec)
        - Storing all would be ~860GB/day for 60 symbols
        - 1/sec sampling = ~86GB/day (10x reduction)

        Args:
            orderbook: OrderBook object

        Returns:
            True if should backup, False otherwise
        """
        symbol_key = f"{orderbook.exchange}:{orderbook.symbol}"
        last_backup = self._last_orderbook_backup.get(symbol_key)
        now = orderbook.timestamp

        if last_backup is None or (now - last_backup).total_seconds() >= 1.0:
            self._last_orderbook_backup[symbol_key] = now
            return True
        return False

    async def _backup_orderbook_to_storage(self, orderbook: OrderBook) -> None:
        """
        Backup order book snapshot to object storage (S3/GCS/Azure Blob)

        Purpose:
        - Long-term storage (replay, analysis)
        - ML training data (order book features)
        - Market microstructure research

        Storage Structure:
        bucket://trading-raw-data-local/orderbooks/
            {year}/{month}/{day}/
                {exchange}-{symbol}-{timestamp}.json

        Example:
        s3://trading-raw-data-local/orderbooks/2025/12/25/
            binance-BTCUSDT-20251225-120000.json

        Args:
            orderbook: OrderBook object
        """
        try:
            # Generate key with partitioning by date
            timestamp = orderbook.timestamp
            year = timestamp.strftime("%Y")
            month = timestamp.strftime("%m")
            day = timestamp.strftime("%d")

            # Filename: {exchange}-{symbol}-{timestamp}.json
            filename = (
                f"{orderbook.exchange}-{orderbook.symbol}-"
                f"{timestamp.strftime('%Y%m%d-%H%M%S')}.json"
            )

            storage_key = f"orderbooks/{year}/{month}/{day}/{filename}"

            # Convert to JSON
            orderbook_json = json.dumps(orderbook.to_dict(), default=str)

            # Upload to storage
            await self.storage_client.upload_file(
                bucket=self.settings.S3_BUCKET_RAW_DATA,
                key=storage_key,
                data=orderbook_json.encode("utf-8"),
            )

        except Exception as e:
            logger.error(f"✗ Storage orderbook backup error: {e}")
            # Don't raise - storage backup is not critical

    async def _flush_orderbooks_to_timeseries_db(self) -> None:
        """
        Batch insert order book snapshots to timeseries database (ClickHouse/TimescaleDB)

        Why batch?
        - 1 insert per orderbook: ~10ms each → 50 orderbooks = 500ms
        - 50 orderbooks in 1 insert: ~50ms total → 10x faster!
        """
        if not self.orderbook_buffer:
            return

        try:
            count = await self.timeseries_db.insert_orderbooks(self.orderbook_buffer)
            logger.info(f"✓ Inserted {count} order book snapshots to timeseries DB")
            self.orderbook_buffer.clear()
        except Exception as e:
            logger.error(f"✗ Timeseries DB orderbook insert error: {e}")
            # Keep buffer for retry

    async def _update_orderbook_cache(self, orderbook: OrderBook) -> None:
        """
        Update latest order book in cache (Redis/Memcached)

        Purpose:
        - Fast API response (GET /orderbook/BTCUSDT)
        - Dashboard current order book visualization
        - Strategy execution (check liquidity before order)

        Cache structure:
        Key: "orderbook:{exchange}:{symbol}"
        Value: {
            "bids": [["50000.00", "0.1"], ...],  # Top 10
            "asks": [["50001.00", "0.15"], ...],
            "best_bid": "50000.00",
            "best_ask": "50001.00",
            "spread": "1.00",
            "mid_price": "50000.50",
            "timestamp": "..."
        }
        TTL: 60 seconds

        Args:
            orderbook: OrderBook object
        """
        try:
            cache_key = f"orderbook:{orderbook.exchange}:{orderbook.symbol}"
            cache_value = json.dumps(
                {
                    "bids": [[str(p), str(q)] for p, q in orderbook.bids[:10]],
                    "asks": [[str(p), str(q)] for p, q in orderbook.asks[:10]],
                    "best_bid": str(orderbook.best_bid[0]) if orderbook.bids else "0",
                    "best_ask": str(orderbook.best_ask[0]) if orderbook.asks else "0",
                    "spread": str(orderbook.spread),
                    "mid_price": str(orderbook.mid_price),
                    "timestamp": orderbook.timestamp.isoformat(),
                }
            )
            await self.cache_client.set(
                cache_key, cache_value, ttl=timedelta(seconds=60)
            )  # 60 sec TTL
        except Exception as e:
            logger.error(f"✗ Cache orderbook error: {e}")
            # Don't raise - not critical

    async def close(self) -> None:
        """
        Cleanup: flush remaining data and close connections

        Called on graceful shutdown (Ctrl+C)
        """
        logger.info("Closing stream processor...")

        # Log validation statistics
        stats = self.validator.get_stats()
        logger.info(
            f"📊 Validation stats: "
            f"Spikes={stats['spike_count']}, "
            f"Invalid={stats['invalid_count']}, "
            f"Symbols={stats['symbols_tracked']}"
        )

        # Flush remaining trades
        if self.trade_buffer:
            logger.info(f"Flushing {len(self.trade_buffer)} remaining trades...")
            await self._flush_to_timeseries_db()

        # Flush remaining order books
        if self.orderbook_buffer:
            logger.info(f"Flushing {len(self.orderbook_buffer)} remaining order books...")
            await self._flush_orderbooks_to_timeseries_db()

        # Close all connections
        await self.stream_client.close()
        await self.storage_client.close()
        await self.timeseries_db.close()
        await self.cache_client.close()

        logger.info("✓ Stream processor closed")
