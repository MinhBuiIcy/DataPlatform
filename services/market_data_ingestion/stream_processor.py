"""
StreamProcessor - Simplified WebSocket to Redis ONLY

Industry Standard Type A:
- WebSocket → Redis (real-time price signals)
- REST API → ClickHouse (authoritative candles via Sync Service)

This processor NO LONGER:
- Writes to ClickHouse (no market_trades table)
- Sends to Kinesis/Kafka stream
- Backs up to S3 storage
- Builds candles from trades
- Batches or queues anything

It ONLY updates Redis cache for real-time price signals.
"""

import json
import logging
from datetime import timedelta

from core.interfaces.cache import BaseCacheClient
from core.models.market_data import OrderBook, Trade

logger = logging.getLogger(__name__)


class StreamProcessor:
    """
    Simplified WebSocket processor - Redis cache ONLY.

    Phase 2 Architecture:
    - WebSocket trades → Redis (latest_price:{exchange}:{symbol})
    - Sync Service → REST API → ClickHouse (authoritative candles)
    - Indicator Service → ClickHouse (scheduled calculations)

    Why Redis only:
    - WebSocket captures only ~4% of trades (sampled)
    - Building candles from WebSocket is inaccurate
    - REST API provides authoritative OHLCV data
    - Redis provides real-time signals for strategies
    """

    def __init__(self, cache_client: BaseCacheClient):
        """
        Initialize processor with Redis client only.

        Args:
            cache_client: Redis client for caching latest prices
        """
        self.cache_client = cache_client
        logger.info("StreamProcessor initialized (Redis ONLY mode)")

    async def connect(self) -> None:
        """Initialize Redis client"""
        await self.cache_client.connect()
        logger.info("✓ Redis cache connected")

    async def process_trade(self, trade: Trade) -> None:
        """
        Process incoming trade - update Redis cache only.

        Stores latest price for real-time signals:
        - Key: latest_price:{exchange}:{symbol}
        - Value: price (float)
        - TTL: 60 seconds

        Args:
            trade: Trade object from WebSocket
        """
        await self._update_cache(trade)

    async def process_orderbook(self, orderbook: OrderBook) -> None:
        """
        Process orderbook - update Redis cache (optional).

        Stores latest bid/ask spreads for strategies.

        Args:
            orderbook: OrderBook object from WebSocket
        """
        # Optional: Store orderbook data if needed by strategies
        key = f"orderbook:{orderbook.exchange}:{orderbook.symbol}"

        # Extract best bid/ask
        best_bid = orderbook.bids[0] if orderbook.bids else None
        best_ask = orderbook.asks[0] if orderbook.asks else None

        if best_bid and best_ask:
            data = {
                "best_bid_price": str(best_bid[0]),
                "best_bid_qty": str(best_bid[1]),
                "best_ask_price": str(best_ask[0]),
                "best_ask_qty": str(best_ask[1]),
                "spread": str(best_ask[0] - best_bid[0]),
                "mid_price": str((best_ask[0] + best_bid[0]) / 2),
                "timestamp": orderbook.timestamp.isoformat(),
            }

            await self.cache_client.set(key, json.dumps(data), ttl_seconds=60)
            logger.debug(
                f"Updated orderbook cache: {orderbook.exchange}:{orderbook.symbol}"
            )

    async def _update_cache(self, trade: Trade) -> None:
        """
        Update latest price in Redis.

        Key format: latest_price:{exchange}:{symbol}
        Value: price (stored as string for precision)
        TTL: 60 seconds

        Args:
            trade: Trade object
        """
        key = f"latest_price:{trade.exchange}:{trade.symbol}"

        await self.cache_client.set(
            key,
            str(trade.price),  # Store as string to preserve precision
            ttl_seconds=60,  # 1 minute expiry
        )

        logger.debug(f"Updated {key} = {trade.price}")

    async def close(self) -> None:
        """Cleanup - close Redis connection"""
        if self.cache_client:
            await self.cache_client.close()
        logger.info("StreamProcessor closed")
